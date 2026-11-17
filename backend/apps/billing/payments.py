"""Restartable payment orchestration. Network calls never hold DB row locks."""
import logging
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.errors import DomainError
from . import services
from .gateways import (CheckoutResult, GatewayDeclined, VerificationResult, get_gateway,
                       payments_enabled, public_origin, valid_redirect)
from .models import Order, OrderStatus, PaymentAttempt, PaymentCheckout, PaymentStatus

logger = logging.getLogger("ft.billing")


def begin_payment(*, user, order_id, idempotency_key):
    # Do not expose another owner's state even when payment is disabled.
    if not Order.objects.filter(pk=order_id, user=user).exists():
        raise DomainError("not_found", "سفارش پیدا نشد.", 404)
    if not payments_enabled():
        raise DomainError("payment_unavailable", "درگاه پرداخت هنوز فعال نیست.", 503)
    attempt = services.create_payment_attempt(user=user, order_id=order_id,
        provider=settings.BILLING_GATEWAY, idempotency_key=idempotency_key)
    # The finance transaction has ended before acquiring the checkout lock.
    checkout, _ = PaymentCheckout.objects.get_or_create(attempt=attempt)
    run_checkout(checkout.pk)
    return payment_payload(Order.objects.get(pk=order_id))


@transaction.atomic
def claim(attempt_id):
    row = PaymentCheckout.objects.select_for_update().filter(pk=attempt_id).first()
    now = timezone.now()
    if not row or row.needs_review or (row.lease_until and row.lease_until > now) or not row.next_check_at or row.next_check_at > now:
        return None
    token = uuid4()
    row.lease_token, row.lease_until = token, now + timedelta(seconds=120)
    row.checks += 1
    row.save(update_fields=["lease_token", "lease_until", "checks", "updated_at"])
    return token


def run_checkout(attempt_id):
    token = claim(attempt_id)
    if token is None:
        return
    row = PaymentCheckout.objects.select_related("attempt__order").get(pk=attempt_id)
    attempt, order = row.attempt, row.attempt.order
    result = None
    code = ""
    review = False
    gateway = None
    initializing = not attempt.provider_reference
    try:
        if order.status != OrderStatus.PENDING:
            code = "delivery"
        else:
            gateway = get_gateway(attempt.provider)
            if initializing:
                # A crashed non-idempotent start may have created a payable link.
                if row.checks > 1 and not gateway.start_is_idempotent:
                    review, code = True, "start_result_unknown"
                elif not settings.BILLING_PAYMENTS_ENABLED or not settings.BILLING_ORDERS_ENABLED:
                    code = "payments_paused"
                elif order.expires_at <= timezone.now() and row.checks == 1:
                    code = "order_expired_before_start"
                else:
                    from .gateways import PaymentRequest
                    result = gateway.start(PaymentRequest(str(attempt.pk), order.amount, order.currency,
                        f"{public_origin()}/api/billing/callback/{row.callback_key}/", f"Order {order.pk}"))
                    if not isinstance(result, CheckoutResult) or not valid_redirect(gateway, result.redirect_url):
                        review, code, result = True, "invalid_gateway_response", None
            else:
                result = gateway.verify(reference=attempt.provider_reference, amount=order.amount, currency=order.currency)
                if not isinstance(result, VerificationResult) or result.status not in ("VERIFIED", "PENDING", "FAILED") or result.reference != attempt.provider_reference:
                    review, code, result = True, "invalid_verification", None
    except GatewayDeclined:
        # Declined is only a valid create result. Verify exceptions are unknown.
        code = "checkout_declined" if initializing else "verification_unavailable"
    except Exception as exc:
        code = "provider_unavailable"
        review = bool(initializing and gateway and not gateway.start_is_idempotent)
        logger.warning("billing.gateway_error", extra={"attempt_id": str(attempt_id), "error_type": type(exc).__name__})

    with transaction.atomic():
        current = PaymentCheckout.objects.select_for_update().get(pk=attempt_id)
        if current.lease_token != token:
            return  # A newer worker owns the result; its retry must be idempotent.
        try:
            if isinstance(result, CheckoutResult):
                services.bind_provider_reference(attempt_id=attempt_id, reference=result.reference)
                current.redirect_url = result.redirect_url
                code = "checkout_ready"
            elif isinstance(result, VerificationResult):
                if result.status == "VERIFIED":
                    services.record_verified_payment(attempt_id=attempt_id, provider_reference=result.reference,
                        transaction_id=result.transaction_id, amount=result.amount, currency=result.currency)
                    code = "verified"
                elif result.status == "FAILED":
                    services.record_failed_payment(attempt_id=attempt_id, result_code="provider_declined")
                    code = "failed"
                else:
                    code = "pending"
            elif code in ("checkout_declined", "order_expired_before_start"):
                services.record_failed_payment(attempt_id=attempt_id, result_code=code)
        except DomainError as exc:
            review, code = True, exc.code
        current.last_code = code
        current.needs_review = review or (current.checks >= 20 and code not in ("verified", "delivery", "checkout_ready", "failed", "checkout_declined", "order_expired_before_start"))
        current.lease_token = current.lease_until = None
        current.next_check_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** min(current.checks, 7)))
        if current.needs_review or code in ("failed", "checkout_declined", "order_expired_before_start"):
            current.next_check_at = None
        current.save()
    # Preserve payment evidence even if entitlement delivery fails.
    if code in ("verified", "delivery"):
        try:
            services.fulfill_order(order.pk)
            PaymentCheckout.objects.filter(pk=attempt_id, lease_token__isnull=True).update(next_check_at=None, last_code="fulfilled")
        except Exception as exc:
            logger.error("billing.delivery_pending", extra={"order_id": str(order.pk), "error_type": type(exc).__name__})


def schedule_check(order):
    row = PaymentCheckout.objects.filter(attempt__order=order).order_by("-attempt__created_at").first()
    if not row or row.needs_review or order.status == OrderStatus.FULFILLED:
        return
    # A bounded cooldown also applies to repeated callbacks and refresh clicks.
    now = timezone.now()
    if row.last_code != "checkout_ready" and row.updated_at > now - timedelta(seconds=10):
        return
    changed = PaymentCheckout.objects.filter(pk=row.pk, needs_review=False, updated_at=row.updated_at).update(
        next_check_at=now, updated_at=now, last_code="check_requested")
    if not changed:
        return
    try:
        from .tasks import process_payment
        process_payment.delay(str(row.pk))
    except Exception:
        # The durable next_check_at is picked up by beat after broker recovery.
        logger.warning("billing.check_queued_for_recovery", extra={"attempt_id": str(row.pk)})


def reconcile_payments(limit=100):
    # Recover a process crash between attempt creation and orchestration setup.
    for attempt in PaymentAttempt.objects.filter(status=PaymentStatus.PENDING,
            provider__in=settings.BILLING_GATEWAY_ADAPTERS, checkout__isnull=True)[:limit]:
        PaymentCheckout.objects.get_or_create(attempt=attempt)
    now = timezone.now()
    ids = list(PaymentCheckout.objects.filter(needs_review=False, next_check_at__lte=now)
        .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now)).order_by("next_check_at").values_list("pk", flat=True)[:limit])
    for attempt_id in ids:
        try:
            run_checkout(attempt_id)
        except Exception as exc:
            logger.error("billing.recovery_failed", extra={"attempt_id": str(attempt_id), "error_type": type(exc).__name__})
    # Includes paid legacy orders and delivery failures unrelated to checkouts.
    for order_id in Order.objects.filter(status=OrderStatus.PAID).values_list("pk", flat=True)[:limit]:
        try:
            services.fulfill_order(order_id)
        except Exception as exc:
            logger.error("billing.delivery_pending", extra={"order_id": str(order_id), "error_type": type(exc).__name__})
    return len(ids)


def payment_payload(order):
    now = timezone.now()
    attempt = order.payment_attempts.order_by("-created_at").first()
    checkout = PaymentCheckout.objects.filter(attempt=attempt).first() if attempt else None
    state = "NOT_STARTED"
    if order.status == OrderStatus.FULFILLED:
        state = "FULFILLED"
    elif order.status == OrderStatus.PAID:
        state = "DELIVERING"
    elif checkout and checkout.needs_review:
        state = "REVIEW"
    elif order.expires_at <= now and (not attempt or attempt.status == PaymentStatus.FAILED):
        # Only a definitive failure can release the customer to a fresh order.
        # Unknown results must stay recoverable even after the quote expires.
        state = "EXPIRED"
    elif attempt:
        state = "FAILED" if attempt.status == PaymentStatus.FAILED else "PENDING"
    redirect = None
    if checkout and checkout.redirect_url and state == "PENDING" and order.expires_at > timezone.now() and payments_enabled():
        try:
            if valid_redirect(get_gateway(attempt.provider), checkout.redirect_url):
                redirect = checkout.redirect_url
                state = "READY"
        except DomainError:
            pass
    return {"order_id": str(order.pk), "state": state, "redirect_url": redirect,
            "can_start": state in ("NOT_STARTED", "FAILED") and order.expires_at > timezone.now() and payments_enabled(),
            "attempt_id": str(attempt.pk) if attempt else None}
