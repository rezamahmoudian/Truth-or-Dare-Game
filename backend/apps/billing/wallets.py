"""Atomic request-credit accounting. Every writer locks Wallet before grants/ledger.

Matcher and chat services invoke these operations under application locks.
"""
from datetime import datetime
import logging

from django.db import transaction
from django.db.models import Case, F, IntegerField, When
from django.utils import timezone

from apps.core.errors import DomainError
from apps.matchmaking.models import MatchTicket, TicketState
from .models import (
    Entitlement, GrantSource, GrantStatus, LedgerKind, MatchCreditReservation,
    ReservationStatus, VIPSubscription, Wallet, WalletLedger,
)

logger = logging.getLogger("ft.billing")


def validate_key(key):
    if not isinstance(key, str) or not key.strip() or len(key) > 100:
        raise DomainError("invalid_idempotency_key", "شناسهٔ درخواست معتبر نیست.")
    return key.strip()


def locked_wallet(user_id):
    # get_or_create handles simultaneous first use through the unique user key.
    wallet, _ = Wallet.objects.get_or_create(user_id=user_id)
    return Wallet.objects.select_for_update().get(pk=wallet.pk)


def post_entry(wallet, grant, *, key, kind, delta=0, reserved_delta=0, reason, reservation=None, actor=None, metadata=None):
    """Private writer. Caller holds the wallet row lock in an atomic transaction."""
    if wallet.balance + delta < 0 or not 0 <= wallet.reserved + reserved_delta <= wallet.balance + delta:
        raise DomainError("invalid_balance", "تغییر موجودی معتبر نیست.", 409)
    entry = WalletLedger.objects.create(
        wallet=wallet, entitlement=grant, reservation=reservation, kind=kind,
        idempotency_key=key, delta=delta, reserved_delta=reserved_delta,
        balance_before=wallet.balance, balance_after=wallet.balance + delta,
        reserved_before=wallet.reserved, reserved_after=wallet.reserved + reserved_delta,
        reason=reason, actor=actor, metadata=metadata or {},
    )
    wallet.balance = entry.balance_after
    wallet.reserved = entry.reserved_after
    wallet.save(update_fields=["balance", "reserved"])
    transaction.on_commit(lambda: logger.info("billing.ledger_recorded", extra={
        "ledger_id": entry.pk, "wallet_id": entry.wallet_id, "kind": entry.kind,
    }))
    from apps.chat import broadcast
    transaction.on_commit(lambda: broadcast.to_users([wallet.user_id], "billing.changed", {
        "ledger_id": entry.pk,
    }), robust=True)
    return entry


def sync_wallet(wallet, now):
    """Lazy lifecycle reconciliation also used by the maintenance command.

    Expiry is recorded once; future renewal credits become usable only when that
    period starts. Read APIs therefore cannot return stale spendable balances.
    """
    expiring = wallet.entitlements.filter(
        status__in=[GrantStatus.ACTIVE, GrantStatus.SCHEDULED], expires_at__lte=now,
    ).order_by("id")
    for grant in expiring:
        if grant.status == GrantStatus.ACTIVE:
            held = list(grant.reservations.filter(status=ReservationStatus.HELD).order_by("id"))
            for reservation in held:
                reservation.status = ReservationStatus.EXPIRED
                reservation.closed_at = now
                reservation.reason = "اعتبار دوره منقضی شد"
                reservation.save(update_fields=["status", "closed_at", "reason"])
                grant.reserved -= 1
                post_entry(wallet, grant, key=f"release:{reservation.pk}", kind=LedgerKind.RELEASE,
                           reserved_delta=-1, reason=reservation.reason, reservation=reservation)
            if grant.remaining:
                post_entry(wallet, grant, key=f"expire:{grant.pk}", kind=LedgerKind.EXPIRE,
                           delta=-grant.remaining, reason="انقضای اعتبار")
        grant.status = GrantStatus.EXPIRED
        grant.remaining = grant.reserved = 0
        grant.save(update_fields=["status", "remaining", "reserved"])
    for grant in wallet.entitlements.filter(status=GrantStatus.SCHEDULED, starts_at__lte=now).order_by("id"):
        activate_grant(wallet, grant)


def activate_grant(wallet, grant, *, key=None, actor=None, reason="افزایش اعتبار", metadata=None):
    grant.status = GrantStatus.ACTIVE
    grant.remaining = grant.amount
    grant.save(update_fields=["status", "remaining"])
    return post_entry(wallet, grant, key=key or f"grant:{grant.pk}", kind=LedgerKind.GRANT,
                      delta=grant.amount, reason=reason, actor=actor, metadata=metadata)


@transaction.atomic
def grant_credits(*, user, amount, actor, reason, idempotency_key, expires_at=None):
    """Audited support grants, including compensation, never silent balance edits."""
    if not actor.is_active or not actor.is_staff or not actor.has_perm("billing.adjust_wallet"):
        raise DomainError("forbidden", "مجوز تغییر اعتبار را نداری.", 403)
    key = "admin:" + validate_key(idempotency_key)
    if type(amount) is not int or not 1 <= amount <= 1000000:
        raise DomainError("invalid_amount", "تعداد اعتبار باید عدد صحیح مثبت باشد.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 240:
        raise DomainError("reason_required", "دلیل ثبت اعتبار را بنویس.")
    if expires_at is not None and (not isinstance(expires_at, datetime) or timezone.is_naive(expires_at)):
        raise DomainError("invalid_expiry", "زمان انقضا باید دارای منطقهٔ زمانی باشد.")
    metadata = {"amount": amount, "expires_at": expires_at.isoformat() if expires_at else None}
    wallet = locked_wallet(user.pk)
    existing = wallet.ledger.filter(idempotency_key=key).first()
    if existing:
        if existing.metadata != metadata or existing.actor_id != actor.pk or existing.reason != reason.strip():
            raise DomainError("idempotency_conflict", "این شناسه قبلاً با اطلاعات دیگری ثبت شده است.", 409)
        return existing.entitlement
    now = timezone.now()
    if expires_at is not None and expires_at <= now:
        raise DomainError("invalid_expiry", "زمان انقضا باید در آینده باشد.")
    sync_wallet(wallet, now)
    grant = Entitlement.objects.create(wallet=wallet, source=GrantSource.ADMIN, amount=amount,
                                       remaining=0, starts_at=now, expires_at=expires_at)
    activate_grant(wallet, grant, key=key, actor=actor, reason=reason.strip(), metadata=metadata)
    return grant


@transaction.atomic
def wallet_snapshot(user):
    from .vip import benefits
    wallet = locked_wallet(user.pk)
    now = timezone.now()
    sync_wallet(wallet, now)
    groups = {source: {"total": 0, "reserved": 0, "available": 0} for source in GrantSource.values}
    for grant in wallet.entitlements.filter(status=GrantStatus.ACTIVE):
        group = groups[grant.source]
        group["total"] += grant.remaining
        group["reserved"] += grant.reserved
        group["available"] += grant.remaining - grant.reserved
    active_vip = VIPSubscription.objects.filter(user=user, revoked_at__isnull=True, starts_at__lte=now, ends_at__gt=now).order_by("starts_at").first()
    return {
        "unit": "REQUEST", "total": wallet.balance, "reserved": wallet.reserved,
        "available": wallet.available, "by_source": groups, "as_of": now,
        "vip": {"active": bool(active_vip), "starts_at": active_vip.starts_at if active_vip else None,
                "ends_at": active_vip.ends_at if active_vip else None,
                "benefits": benefits(active_vip.benefits) if active_vip else {}, "auto_renew": False},
    }


def owned_ticket(user, ticket_id):
    try:
        return MatchTicket.objects.select_related("mode").get(pk=ticket_id, user=user)
    except MatchTicket.DoesNotExist:
        raise DomainError("not_found", "درخواست بازی پیدا نشد.", 404)


@transaction.atomic
def reserve_credit(*, user, ticket_id):
    wallet = locked_wallet(user.pk)
    sync_wallet(wallet, timezone.now())
    ticket = owned_ticket(user, ticket_id)
    existing = MatchCreditReservation.objects.filter(ticket=ticket).first()
    if existing:
        return existing  # A released or consumed ticket is never resurrected.
    if ticket.state not in [TicketState.QUEUED, TicketState.MATCHED] or ticket.quota_closed_at or ticket.quota_consumed_at or ticket.mode.is_ai:
        raise DomainError("invalid_ticket", "این درخواست قابل رزرو اعتبار نیست.", 409)
    grant = wallet.entitlements.filter(status=GrantStatus.ACTIVE, remaining__gt=F("reserved")).order_by(
        Case(When(source=GrantSource.VIP, then=0), default=1, output_field=IntegerField()),
        F("expires_at").asc(nulls_last=True), "id",
    ).first()
    if not grant:
        raise DomainError("insufficient_credit", "اعتبار درخواست ویژه کافی نیست.", 409)
    reservation = MatchCreditReservation.objects.create(ticket=ticket, entitlement=grant)
    grant.reserved += 1
    grant.save(update_fields=["reserved"])
    post_entry(wallet, grant, key=f"reserve:{reservation.pk}", kind=LedgerKind.RESERVE,
               reserved_delta=1, reason="رزرو برای جستجوی هم‌بازی", reservation=reservation)
    return reservation


@transaction.atomic
def release_credit(*, user, ticket_id, reason="جستجو پایان یافت"):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 240:
        raise DomainError("reason_required", "دلیل آزادسازی معتبر نیست.")
    wallet = locked_wallet(user.pk)
    now = timezone.now()
    sync_wallet(wallet, now)
    ticket = owned_ticket(user, ticket_id)
    reservation = MatchCreditReservation.objects.filter(ticket=ticket).select_related("entitlement").first()
    if not reservation or reservation.status != ReservationStatus.HELD:
        return reservation
    grant = reservation.entitlement
    grant.reserved -= 1
    grant.save(update_fields=["reserved"])
    reservation.status = ReservationStatus.RELEASED
    reservation.closed_at = now
    reservation.reason = reason.strip()
    reservation.save(update_fields=["status", "closed_at", "reason"])
    post_entry(wallet, grant, key=f"release:{reservation.pk}", kind=LedgerKind.RELEASE,
               reserved_delta=-1, reason=reservation.reason, reservation=reservation)
    return reservation


@transaction.atomic
def consume_credit(*, user, ticket_id):
    wallet = locked_wallet(user.pk)
    now = timezone.now()
    sync_wallet(wallet, now)
    ticket = owned_ticket(user, ticket_id)
    reservation = MatchCreditReservation.objects.filter(ticket=ticket).select_related("entitlement").first()
    if not reservation:
        raise DomainError("reservation_required", "رزرو اعتبار پیدا نشد.", 409)
    if reservation.status != ReservationStatus.HELD:
        return reservation
    # The existing engagement rule is still authoritative. A room alone is insufficient.
    if ticket.state != TicketState.MATCHED or not ticket.quota_consumed_at or ticket.quota_closed_at or (ticket.mode.is_ai and not ticket.uses_credit):
        raise DomainError("match_not_engaged", "این مچ هنوز واجد شرایط مصرف اعتبار نیست.", 409)
    from apps.chat.models import Participant
    if ticket.conversation_id and Participant.objects.filter(conversation_id=ticket.conversation_id, user__is_ai=True).exists():
        raise DomainError("human_match_required", "اعتبار مچ انسانی برای بازی AI مصرف نمی‌شود.", 409)
    grant = reservation.entitlement
    grant.remaining -= 1
    grant.reserved -= 1
    grant.save(update_fields=["remaining", "reserved"])
    reservation.status = ReservationStatus.CONSUMED
    reservation.closed_at = now
    reservation.reason = "مچ و تعامل دوطرفه"
    reservation.save(update_fields=["status", "closed_at", "reason"])
    post_entry(wallet, grant, key=f"consume:{reservation.pk}", kind=LedgerKind.CONSUME,
               delta=-1, reserved_delta=-1, reason=reservation.reason, reservation=reservation)
    return reservation
