"""Orders and trusted payment verification boundary, independent of any gateway.

Only a trusted server-side provider adapter may call record_verified_payment.
There is deliberately no HTTP endpoint that accepts a client 'payment success'.
"""
from copy import deepcopy
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.core.errors import DomainError
from .models import (
    Entitlement, GrantSource, Order, OrderStatus, PaymentAttempt, PaymentStatus,
    ProductKind, ProductOffer, VIPSubscription,
)
from .wallets import locked_wallet, sync_wallet, validate_key


def available_offers(now=None):
    return ProductOffer.objects.filter(is_active=True, product__is_active=True, starts_at__lte=now or timezone.now()).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now or timezone.now()),
    ).select_related("product").order_by("product__sort_order", "id")


@transaction.atomic
def create_order(*, user, offer_id, idempotency_key):
    key = validate_key(idempotency_key)
    locked_wallet(user.pk)
    existing = Order.objects.filter(user=user, idempotency_key=key).first()
    if existing:
        if existing.offer_id != offer_id:
            raise DomainError("idempotency_conflict", "این شناسه برای سفارش دیگری استفاده شده است.", 409)
        return existing
    if not settings.BILLING_ORDERS_ENABLED:
        raise DomainError("billing_unavailable", "خرید هنوز فعال نشده است.", 503)
    now = timezone.now()
    offer = available_offers(now).filter(pk=offer_id, channel="web").first()
    if not offer:
        raise DomainError("offer_unavailable", "این پیشنهاد فروش در دسترس نیست.", 409)
    product = offer.product
    from .vip import active_period, benefits, price_for
    quote = price_for(offer, active_period(user.pk, now))
    from .items import purchasable_snapshot
    item_data = purchasable_snapshot(user, product) if product.kind == ProductKind.ITEM else None
    return Order.objects.create(
        user=user, offer=offer, idempotency_key=key, amount=quote["amount"], currency=offer.currency,
        expires_at=now + timedelta(minutes=max(1, settings.BILLING_ORDER_TTL_MINUTES)),
        product_snapshot={
            "version": 1, "key": product.key, "title": product.title, "kind": product.kind,
            "credits": product.credits, "duration_days": product.duration_days,
            "credit_validity_days": product.credit_validity_days, "benefits": benefits(product.benefits) if product.kind == ProductKind.VIP else deepcopy(product.benefits),
            "pricing": quote,
            **({"item": item_data} if item_data else {}),
            "offer_key": offer.key, "channel": offer.channel, "original_amount": offer.original_amount,
        },
    )


def owned_order(user, order_id):
    try:
        return Order.objects.select_for_update().get(pk=order_id, user=user)
    except Order.DoesNotExist:
        raise DomainError("not_found", "سفارش پیدا نشد.", 404)


def short_text(value, maximum, code="invalid_reference"):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DomainError(code, "شناسهٔ پرداخت معتبر نیست.")
    return value.strip()


@transaction.atomic
def create_payment_attempt(*, user, order_id, provider, idempotency_key):
    key = validate_key(idempotency_key)
    provider = short_text(provider, 40)
    locked_wallet(user.pk)
    order = owned_order(user, order_id)
    existing = order.payment_attempts.filter(idempotency_key=key).first()
    if existing:
        if existing.provider != provider:
            raise DomainError("idempotency_conflict", "درگاه این درخواست تغییر کرده است.", 409)
        return existing
    if order.status != OrderStatus.PENDING or order.expires_at <= timezone.now():
        raise DomainError("order_not_payable", "سفارش قابل پرداخت نیست.", 409)
    # Do not start a second checkout while the first result is unknown.
    if order.payment_attempts.filter(status=PaymentStatus.PENDING).exists():
        raise DomainError("payment_pending", "ابتدا نتیجهٔ پرداخت قبلی را بررسی کن.", 409)
    if not settings.BILLING_ORDERS_ENABLED:
        raise DomainError("billing_unavailable", "خرید هنوز فعال نشده است.", 503)
    return PaymentAttempt.objects.create(order=order, provider=provider, idempotency_key=key)


def locked_attempt(attempt_id):
    try:
        owner_id = PaymentAttempt.objects.values_list("order__user_id", flat=True).get(pk=attempt_id)
    except PaymentAttempt.DoesNotExist:
        raise DomainError("not_found", "تلاش پرداخت پیدا نشد.", 404)
    wallet = locked_wallet(owner_id)
    attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
    order = Order.objects.select_for_update().get(pk=attempt.order_id)
    return wallet, order, attempt


@transaction.atomic
def bind_provider_reference(*, attempt_id, reference):
    reference = short_text(reference, 200)
    _, _, attempt = locked_attempt(attempt_id)
    if attempt.provider_reference:
        if attempt.provider_reference != reference:
            raise DomainError("reference_conflict", "شناسهٔ درگاه قابل جایگزینی نیست.", 409)
        return attempt
    try:
        with transaction.atomic():
            attempt.provider_reference = reference
            attempt.save(update_fields=["provider_reference"])
    except IntegrityError:
        raise DomainError("reference_conflict", "این شناسهٔ درگاه قبلاً ثبت شده است.", 409)
    return attempt


@transaction.atomic
def record_failed_payment(*, attempt_id, result_code):
    """Only for a definitive provider failure, never a timeout or closed browser."""
    _, order, attempt = locked_attempt(attempt_id)
    if attempt.status == PaymentStatus.VERIFIED or order.status != OrderStatus.PENDING:
        return attempt
    attempt.status = PaymentStatus.FAILED
    attempt.result_code = short_text(result_code, 64)
    attempt.save(update_fields=["status", "result_code"])
    return attempt


@transaction.atomic
def record_verified_payment(*, attempt_id, provider_reference, transaction_id, amount, currency):
    """Trusted internal adapter input AFTER provider verification, not callback data.

    Verification and delivery are separate commits so paid-but-undelivered orders
    can be retried safely. Late verification uses the immutable quoted price.
    """
    transaction_id = short_text(transaction_id, 200)
    _, order, attempt = locked_attempt(attempt_id)
    if not attempt.provider_reference or provider_reference != attempt.provider_reference:
        raise DomainError("reference_mismatch", "شناسهٔ پرداخت با سفارش مطابقت ندارد.", 409)
    if type(amount) is not int or amount != order.amount or currency != order.currency:
        raise DomainError("payment_mismatch", "مبلغ یا واحد پرداخت با سفارش مطابقت ندارد.", 409)
    if attempt.status == PaymentStatus.VERIFIED:
        if attempt.transaction_id != transaction_id:
            raise DomainError("transaction_conflict", "شمارهٔ تراکنش تغییر کرده است.", 409)
        return order
    if order.status != OrderStatus.PENDING:
        raise DomainError("order_already_paid", "این سفارش قبلاً پرداخت شده و نیاز به بررسی دارد.", 409)
    now = timezone.now()
    try:
        with transaction.atomic():
            attempt.status = PaymentStatus.VERIFIED
            attempt.transaction_id = transaction_id
            attempt.verified_amount = amount
            attempt.verified_currency = currency
            attempt.verified_at = now
            attempt.result_code = "verified"
            attempt.save(update_fields=["status", "transaction_id", "verified_amount", "verified_currency", "verified_at", "result_code"])
    except IntegrityError:
        raise DomainError("transaction_conflict", "این تراکنش قبلاً برای پرداخت دیگری ثبت شده است.", 409)
    order.status = OrderStatus.PAID
    order.paid_at = now
    order.save(update_fields=["status", "paid_at"])
    return order


@transaction.atomic
def fulfill_order(order_id):
    try:
        user_id = Order.objects.values_list("user_id", flat=True).get(pk=order_id)
    except Order.DoesNotExist:
        raise DomainError("not_found", "سفارش پیدا نشد.", 404)
    wallet = locked_wallet(user_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == OrderStatus.FULFILLED:
        return order
    if order.status != OrderStatus.PAID or not order.payment_attempts.filter(status=PaymentStatus.VERIFIED, verified_amount=order.amount, verified_currency=order.currency).exists():
        raise DomainError("payment_required", "پرداخت سفارش تأیید نشده است.", 409)
    now = timezone.now()
    sync_wallet(wallet, now)
    data = order.product_snapshot
    starts_at = now
    expires_at = None
    source = GrantSource.PURCHASE
    if data["kind"] == ProductKind.VIP:
        last_end = VIPSubscription.objects.filter(user_id=user_id, revoked_at__isnull=True, ends_at__gt=now).aggregate(end=Max("ends_at"))["end"]
        starts_at = max(now, last_end) if last_end else now
        expires_at = starts_at + timedelta(days=data["duration_days"])
        VIPSubscription.objects.create(user_id=user_id, order=order, starts_at=starts_at,
                                       ends_at=expires_at, benefits=data["benefits"])
        source = GrantSource.VIP
    elif data["kind"] == ProductKind.CREDITS:
        if data["credit_validity_days"]:
            expires_at = starts_at + timedelta(days=data["credit_validity_days"])
    elif data["kind"] == ProductKind.ITEM:
        from .items import deliver
        deliver(order)
    else:
        raise DomainError("unsupported_product", "نوع محصول پشتیبانی نمی‌شود.", 409)
    if data["credits"]:
        Entitlement.objects.create(wallet=wallet, order=order, source=source, amount=data["credits"],
                                   remaining=0, starts_at=starts_at, expires_at=expires_at)
        sync_wallet(wallet, now)
    order.status = OrderStatus.FULFILLED
    order.fulfilled_at = now
    order.save(update_fields=["status", "fulfilled_at"])
    if data["kind"] == ProductKind.VIP:
        from .vip import notify_change
        transaction.on_commit(lambda: notify_change(user_id), robust=True)
    return order
