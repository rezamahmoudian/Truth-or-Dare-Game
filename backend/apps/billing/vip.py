"""VIP capabilities derived from paid subscription periods, never client flags."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.errors import DomainError
from .models import ProductKind, VIPSubscription, VIPSpotlight
from .wallets import locked_wallet, validate_key


DEFAULT_BENEFITS = {
    "gold_profile": True, "vip_badge": True, "exclusive_frame": True,
    "queue_priority_seconds": 60, "request_discount_percent": 10,
    "spotlight_uses": 1, "spotlight_minutes": 15, "ad_free": True,
}
LIMITS = {"queue_priority_seconds": (0, 120), "request_discount_percent": (0, 30),
          "spotlight_uses": (0, 10), "spotlight_minutes": (1, 60)}


def benefits(data):
    """Legacy periods receive base benefits; invalid values fail closed."""
    data = data if isinstance(data, dict) else {}
    result = {}
    for key, default in DEFAULT_BENEFITS.items():
        value = data.get(key, default)
        if key in LIMITS:
            low, high = LIMITS[key]
            result[key] = value if type(value) is int and low <= value <= high else low
        else:
            result[key] = value is True
    return result


def active_periods(now=None):
    now = now or timezone.now()
    return VIPSubscription.objects.filter(revoked_at__isnull=True, starts_at__lte=now, ends_at__gt=now,
                                         user__is_active=True, user__is_ai=False).order_by("starts_at", "pk")


def active_period(user_id, now=None):
    return active_periods(now).filter(user_id=user_id).first()


def public_status(user_id, period, now, cosmetics=None):
    if cosmetics is None:
        from .items import looks_for_ids
        cosmetics = looks_for_ids([user_id]).get(user_id, {})
    perks = benefits(period.benefits) if period else {}
    return {"user_id": user_id, "active": bool(period), "as_of": now.isoformat(),
            "cosmetics": {slot: {"visual": value["visual"], "title": value["title"]} for slot, value in cosmetics.items()},
            "ends_at": period.ends_at.isoformat() if period else None,
            **{key: perks.get(key, False) for key in ("gold_profile", "vip_badge", "exclusive_frame")}}


def hydrate(users):
    """One query per response collection, including duplicate sender instances."""
    users = list(users)
    pending = [user for user in users if user and not hasattr(user, "_public_vip")]
    if not pending:
        return users
    now = timezone.now()
    periods = {}
    from .items import looks_for_ids
    looks = looks_for_ids({user.pk for user in pending})
    for period in active_periods(now).filter(user_id__in={user.pk for user in pending}):
        periods.setdefault(period.user_id, period)
    for user in pending:
        user._public_vip = public_status(user.pk, periods.get(user.pk), now, looks.get(user.pk, {}))
    return users


def for_user(user):
    if hasattr(user, "_public_vip"):
        return user._public_vip
    now = timezone.now()
    return public_status(user.pk, active_period(user.pk, now), now)


def price_for(offer, period):
    percent = benefits(period.benefits)["request_discount_percent"] if period and offer.product.kind == ProductKind.CREDITS else 0
    # Round up to an integer rial; no floating-point financial arithmetic.
    amount = max(1, (offer.amount * (100 - percent) + 99) // 100)
    return {"amount": amount, "base_amount": offer.amount, "vip_discount_percent": percent,
            "vip_subscription_id": period.pk if percent else None}


def membership(user):
    now = timezone.now()
    period = active_period(user.pk, now)
    perks = benefits(period.benefits) if period else {}
    spots = VIPSpotlight.objects.filter(subscription=period) if period else VIPSpotlight.objects.none()
    active_spot = spots.filter(ends_at__gt=now).first()
    upcoming = VIPSubscription.objects.filter(user=user, revoked_at__isnull=True, starts_at__gt=now).order_by("starts_at").first()
    return {**public_status(user.pk, period, now), "starts_at": period.starts_at if period else None,
            "benefits": perks, "auto_renew": False,
            "next_period": {"starts_at": upcoming.starts_at, "ends_at": upcoming.ends_at} if upcoming else None,
            "spotlight": {"remaining": max(0, perks.get("spotlight_uses", 0) - spots.count()),
                          "ends_at": active_spot.ends_at if active_spot else None}}


@transaction.atomic
def activate_spotlight(*, user, idempotency_key):
    key = validate_key(idempotency_key)
    locked_wallet(user.pk)  # Serializes activation with fulfillment and revocation.
    existing = VIPSpotlight.objects.filter(subscription__user=user, idempotency_key=key).first()
    if existing:
        return existing
    now = timezone.now()
    period = active_period(user.pk, now)
    if not period:
        raise DomainError("vip_required", "برای Spotlight باید عضویت VIP فعال داشته باشی.", 403)
    if not user.is_onboarded:
        raise DomainError("profile_incomplete", "اول پروفایلت را کامل کن.", 409)
    perks = benefits(period.benefits)
    from .items import spotlight_active
    if spotlight_active(user.pk):
        raise DomainError("spotlight_active", "Spotlight تو هنوز فعاله.", 409)
    if period.spotlights.count() >= perks["spotlight_uses"]:
        raise DomainError("spotlight_used", "Spotlight این دوره را استفاده کردی.", 409)
    spot = VIPSpotlight.objects.create(subscription=period, idempotency_key=key, starts_at=now,
        ends_at=min(period.ends_at, now + timedelta(minutes=perks["spotlight_minutes"])))
    transaction.on_commit(lambda: notify_change(user.pk), robust=True)
    return spot


def notify_change(user_id):
    """Invalidate the member and existing social contacts without global fanout."""
    from apps.chat import broadcast
    from apps.chat.models import Participant
    from apps.users.models import Friendship
    conversations = Participant.objects.filter(user_id=user_id).values("conversation_id")
    peers = set(Participant.objects.filter(conversation_id__in=conversations, left_at__isnull=True).values_list("user_id", flat=True))
    for a, b in Friendship.objects.filter(Q(from_user_id=user_id) | Q(to_user_id=user_id)).values_list("from_user_id", "to_user_id"):
        peers.update((a, b))
    peers.add(user_id)
    now = timezone.now()
    broadcast.to_users(list(peers), "user.vip_changed", {"vip": public_status(user_id, active_period(user_id, now), now)})
    broadcast.to_users([user_id], "billing.changed", {})
