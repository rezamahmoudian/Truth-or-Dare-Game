"""Optional rewarded-ad adapter. No client 'watched' endpoint can award goods.

A provider must verify its S2S callback signature AND bind its external event
to the server-created session ID. Register only a production adapter here after
testing against that provider's official sandbox. There is no demo provider.
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from apps.core.errors import DomainError
from .models import DigitalItem, InventoryGrant, RewardSession
from .wallets import locked_wallet
from .items import snapshot, changed_later


@dataclass(frozen=True)
class VerifiedReward:
    session_id: str
    event_id: str


class RewardProvider(Protocol):
    def launch(self, session: RewardSession) -> dict:
        """Return provider-specific SDK configuration, never a reward flag."""
    def verify_callback(self, request) -> VerifiedReward:
        """Reject invalid signature, audience, timestamps or incomplete viewing."""


PROVIDERS: dict[str, RewardProvider] = {}


def provider():
    key = getattr(settings, "REWARDED_AD_PROVIDER", "")
    return key, PROVIDERS.get(key) if getattr(settings, "REWARDED_ADS_ENABLED", False) else None


def status():
    key, adapter = provider()
    return {"available": bool(adapter), "provider": key if adapter else None,
            "daily_limit": min(5, max(1, getattr(settings, "REWARDED_AD_DAILY_LIMIT", 1)))}


@transaction.atomic
def start(user):
    key, adapter = provider()
    if not adapter:
        raise DomainError("ads_unavailable", "تبلیغ جایزه‌ای هنوز فعال نیست.", 503)
    locked_wallet(user.pk)
    if not user.is_onboarded or user.is_ai or not user.is_active:
        raise DomainError("profile_incomplete", "پروفایل کامل لازم است.", 403)
    now = timezone.now()
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if RewardSession.objects.filter(user=user, claimed_at__gte=since).count() >= status()["daily_limit"]:
        raise DomainError("reward_limit", "جایزهٔ امروز را دریافت کرده‌ای.", 429)
    existing = RewardSession.objects.filter(user=user, provider=key, claimed_at__isnull=True, expires_at__gt=now).first()
    if existing:
        return existing
    item = DigitalItem.objects.select_related("product").filter(product__key=getattr(settings, "REWARDED_ITEM_KEY", ""), kind="SPOTLIGHT").first()
    if not item or item.units != 1 or item.spotlight_minutes > 5:
        raise DomainError("reward_unconfigured", "جایزهٔ تبلیغ تنظیم نشده است.", 503)
    return RewardSession.objects.create(user=user, item=item, provider=key, snapshot=snapshot(item), expires_at=now + timedelta(minutes=15))


@transaction.atomic
def grant_verified(provider_key, proof: VerifiedReward):
    # Called only after the registered adapter verifies the external evidence.
    row = RewardSession.objects.filter(pk=proof.session_id, provider=provider_key).first()
    if not row or not isinstance(proof.event_id, str) or not 1 <= len(proof.event_id) <= 100:
        raise DomainError("invalid_reward", "مدرک جایزه معتبر نیست.", 400)
    locked_wallet(row.user_id)
    row.refresh_from_db()
    if row.claimed_at:
        if row.event_id != proof.event_id:
            raise DomainError("reward_conflict", "مدرک جایزه تغییر کرده است.", 409)
        return row.grant
    now = timezone.now()
    if row.expires_at <= now or not row.user.is_active:
        raise DomainError("reward_expired", "مهلت جایزه تمام شده است.", 409)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if RewardSession.objects.filter(user_id=row.user_id, claimed_at__gte=since).count() >= status()["daily_limit"]:
        raise DomainError("reward_limit", "سقف جایزهٔ امروز پر شده است.", 429)
    try:
        with transaction.atomic():
            grant = InventoryGrant.objects.create(user_id=row.user_id, item_id=row.item_id, snapshot=row.snapshot,
                reward_key=f"ad:{provider_key}:{proof.event_id}", quantity=1, remaining=1)
    except IntegrityError:
        raise DomainError("reward_conflict", "این مدرک قبلاً برای جایزه استفاده شده است.", 409)
    row.claimed_at, row.event_id, row.grant = now, proof.event_id, grant
    row.save(update_fields=["claimed_at", "event_id", "grant"])
    changed_later(row.user_id)
    return grant
