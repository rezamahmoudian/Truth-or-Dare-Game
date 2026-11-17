"""Audited support writes. Checkout -> Wallet -> financial rows; no bank I/O."""
from hashlib import sha256

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.errors import DomainError
from .models import (Entitlement, GrantStatus, LedgerKind, Order, OrderStatus,
                     PaymentCheckout, PaymentStatus, SupportOperation, VIPSubscription)
from .services import fulfill_order
from .wallets import grant_credits, locked_wallet, post_entry, sync_wallet, validate_key


ACTIONS = {
    "grant": ("افزایش / جبران اعتبار", "billing.adjust_wallet", "نام کاربری"),
    "debit": ("کاهش اعتبار استفاده‌نشده", "billing.debit_wallet", "شناسه اعتبار اختصاص‌یافته"),
    "revoke_vip": ("لغو دوره VIP و اعتبار استفاده‌نشده آن", "billing.revoke_vip", "شناسه دوره VIP"),
    "retry_delivery": ("تحویل دوباره سفارش پرداخت‌شده", "billing.retry_delivery", "شناسه سفارش"),
    "review_payment": ("ازسرگیری استعلام پرداخت", "billing.review_payments", "شناسه تلاش پرداخت"),
}


def require_permission(actor, action):
    if action not in ACTIONS or not actor.is_active or not actor.is_staff or not actor.has_perm(ACTIONS[action][1]):
        raise DomainError("forbidden", "مجوز این عملیات مالی را نداری.", 403)


@transaction.atomic
def execute(*, actor, action, target, reason, idempotency_key, amount=None, expected_user_id=None):
    require_permission(actor, action)
    key = validate_key(idempotency_key)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 240:
        raise DomainError("reason_required", "دلیل عملیات را بنویس (حداکثر ۲۴۰ حرف).")
    reason = reason.strip()
    if action in ("grant", "debit"):
        if type(amount) is not int or not 1 <= amount <= 1000000:
            raise DomainError("invalid_amount", "تعداد اعتبار باید بین ۱ تا ۱۰۰۰۰۰۰ باشد.")
    elif amount is not None:
        raise DomainError("invalid_amount", "این عملیات تعداد اعتبار نمی‌پذیرد.")
    checkout = None
    try:
        if action == "grant":
            user = get_user_model().objects.get(username=target)
            target = str(user.pk)
        elif action == "debit":
            grant = Entitlement.objects.select_related("wallet__user").get(pk=target)
            user, target = grant.wallet.user, str(grant.pk)
        elif action == "revoke_vip":
            vip = VIPSubscription.objects.select_related("user").get(pk=target)
            user, target = vip.user, str(vip.pk)
        elif action == "retry_delivery":
            order = Order.objects.select_related("user").get(pk=target)
            user, target = order.user, str(order.pk)
        else:
            # Never acquire Checkout after Wallet: workers use the reverse order.
            checkout = PaymentCheckout.objects.select_for_update().get(pk=target)
            order = checkout.attempt.order
            user, target = order.user, str(checkout.pk)
    except (get_user_model().DoesNotExist, Entitlement.DoesNotExist, VIPSubscription.DoesNotExist,
            Order.DoesNotExist, PaymentCheckout.DoesNotExist, ValueError, ValidationError, OverflowError):
        raise DomainError("not_found", "کاربر یا رکورد مالی پیدا نشد.", 404) from None
    if expected_user_id is not None and user.pk != expected_user_id:
        raise DomainError("target_changed", "مالک رکورد نسبت به پیش‌نمایش تغییر کرده؛ دوباره بررسی کن.", 409)
    wallet = locked_wallet(user.pk)
    parameters = {"amount": amount}
    existing = SupportOperation.objects.filter(wallet=wallet, idempotency_key=key).first()
    if existing:
        if (existing.actor_id, existing.action, existing.target, existing.reason, existing.parameters) != (actor.pk, action, target, reason, parameters):
            raise DomainError("idempotency_conflict", "این درخواست قبلاً با اطلاعات دیگری ثبت شده است.", 409)
        return existing
    now = timezone.now()
    result = {}
    if action == "grant":
        grant = grant_credits(user=user, amount=amount, actor=actor, reason=reason,
                              idempotency_key="support:" + sha256(key.encode()).hexdigest())
        result = {"entitlement_id": grant.pk, "credits_added": amount}
    elif action == "debit":
        sync_wallet(wallet, now)
        grant = Entitlement.objects.get(pk=target)
        if grant.status != GrantStatus.ACTIVE or amount > grant.remaining - grant.reserved:
            raise DomainError("unavailable_credit", "فقط اعتبار فعال و رزرو‌نشده قابل کاهش است.", 409)
        grant.remaining -= amount
        grant.save(update_fields=["remaining"])
        post_entry(wallet, grant, key="support-debit:" + key, kind=LedgerKind.ADJUST,
                   delta=-amount, actor=actor, reason=reason)
        result = {"credits_removed": amount}
    elif action == "revoke_vip":
        sync_wallet(wallet, now)
        vip = VIPSubscription.objects.select_for_update().get(pk=target)
        if vip.revoked_at or vip.ends_at <= now:
            raise DomainError("vip_closed", "این دوره قبلاً لغو شده یا پایان یافته است.", 409)
        grant = Entitlement.objects.filter(order_id=vip.order_id).first()
        if grant and grant.reserved:
            raise DomainError("credit_reserved", "این دوره اعتبار رزروشده دارد؛ پس از پایان جستجو یا تعیین تکلیف مچ دوباره اقدام کن.", 409)
        removed = grant.remaining if grant else 0
        if grant:
            if removed:
                post_entry(wallet, grant, key="support-vip:" + key, kind=LedgerKind.ADJUST,
                           delta=-removed, actor=actor, reason=reason)
            grant.remaining = 0
            grant.status = GrantStatus.REVOKED
            grant.save(update_fields=["remaining", "status"])
        vip.revoked_at = now
        vip.save(update_fields=["revoked_at"])
        from .vip import notify_change
        transaction.on_commit(lambda: notify_change(user.pk), robust=True)
        result = {"credits_removed": removed, "vip_id": vip.pk}
        from apps.chat import broadcast
        transaction.on_commit(lambda: broadcast.to_users([user.pk], "billing.changed", {}), robust=True)
    elif action == "retry_delivery":
        order = fulfill_order(target)  # Checks immutable bank evidence; exactly once.
        result = {"order_id": str(order.pk), "status": order.status}
    else:
        attempt = checkout.attempt
        attempt.refresh_from_db()
        order.refresh_from_db()
        if checkout.lease_until and checkout.lease_until > now:
            raise DomainError("payment_busy", "استعلام دیگری در حال اجراست؛ کمی بعد دوباره اقدام کن.", 409)
        if attempt.status != PaymentStatus.PENDING or order.status != OrderStatus.PENDING:
            raise DomainError("payment_closed", "این پرداخت دیگر منتظر استعلام نیست.", 409)
        # No manual reference binding or replay of an unknown checkout creation.
        # A bound reference allows ONLY bank verification, never a second charge.
        if not attempt.provider_reference:
            raise DomainError("reference_required", "شناسه درگاه ثبت نشده؛ نتیجه نامعلوم ساخت پرداخت باید با پشتیبانی درگاه بررسی شود.", 409)
        if checkout.last_code == "support_check_requested" and checkout.next_check_at:
            raise DomainError("already_scheduled", "این استعلام قبلاً در صف بررسی قرار گرفته است.", 409)
        checkout.needs_review = False
        checkout.lease_token = checkout.lease_until = None
        checkout.next_check_at = now
        checkout.last_code = "support_check_requested"
        # Keep lifetime check count. An unresolved retry returns to review again.
        checkout.save()
        result = {"attempt_id": str(checkout.pk), "state": "scheduled"}
        transaction.on_commit(lambda: dispatch_check(str(checkout.pk)), robust=True)
    return SupportOperation.objects.create(wallet=wallet, actor=actor, action=action, target=target,
        reason=reason, parameters=parameters, result=result, idempotency_key=key)


def dispatch_check(attempt_id):
    from .tasks import process_payment
    process_payment.delay(attempt_id)  # Durable next_check_at survives broker failure.
