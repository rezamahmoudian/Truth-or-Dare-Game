"""Server-owned delivery, ownership, appearance and consumable use."""
from datetime import timedelta
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils import timezone
from apps.core.errors import DomainError
from .item_models import CONSUMABLE, EQUIPPABLE, VISUALS
from .models import DigitalItem, InventoryGrant, ItemUse, UserAppearance, Order
from .wallets import locked_wallet, validate_key


def snapshot(item):
    result = {"id": item.pk, "kind": item.kind, "visual": item.visual, "title": item.product.title,
              "units": item.units, "spotlight_minutes": item.spotlight_minutes}
    if item.kind == "PACK":
        count = getattr(item, "approved_prompt_count", None)
        result["prompt_count"] = count if count is not None else item.prompts.filter(is_active=True, review_status="APPROVED").count()
    return result


def purchasable_snapshot(user, product):
    item = DigitalItem.objects.filter(product=product).select_related("product").first()
    if not item:
        raise DomainError("item_unavailable", "این آیتم هنوز آمادهٔ فروش نیست.", 409)
    try:
        item.full_clean()
    except ValidationError:
        raise DomainError("item_unavailable", "تنظیمات این آیتم نیاز به بررسی دارد.", 409)
    if item.kind not in CONSUMABLE:
        if InventoryGrant.objects.filter(user=user, item=item).exists():
            raise DomainError("already_owned", "این آیتم را از قبل داری.", 409)
        if Order.objects.filter(user=user, offer__product=product).filter(Q(status="PAID") | Q(status="PENDING", expires_at__gt=timezone.now()) | Q(status="PENDING", payment_attempts__status="PENDING")).exists():
            raise DomainError("purchase_pending", "ابتدا سفارش قبلی این آیتم را در تاریخچه بررسی کن.", 409)
    if item.kind == "PACK" and not item.prompts.filter(is_active=True, review_status="APPROVED").exists():
        raise DomainError("pack_not_ready", "سؤال‌های این بسته هنوز تأیید نشده‌اند.", 409)
    return snapshot(item)


def deliver(order):
    data = order.product_snapshot["item"]
    InventoryGrant.objects.create(user=order.user, item_id=data["id"], order=order, snapshot=data,
                                  quantity=data["units"], remaining=data["units"])
    changed_later(order.user_id)


def changed_later(user_id):
    from .vip import notify_change
    transaction.on_commit(lambda: notify_change(user_id), robust=True)


def looks_for_ids(ids):
    return dict(UserAppearance.objects.filter(user_id__in=ids).values_list("user_id", "slots"))


def inventory(user):
    slots = looks_for_ids([user.pk]).get(user.pk, {})
    active = ItemUse.objects.filter(user=user, ends_at__gt=timezone.now()).order_by("-ends_at").first()
    return {"slots": slots, "spotlight_ends_at": active.ends_at if active else None,
            "items": [{"id": g.pk, "item": g.snapshot, "remaining": g.remaining,
                       "equipped": slots.get(g.snapshot["kind"], {}).get("grant_id") == g.pk}
                      for g in InventoryGrant.objects.filter(user=user).order_by("-pk")]}


def owned(user, grant_id):
    row = InventoryGrant.objects.filter(pk=grant_id, user=user).first()
    if not row:
        raise DomainError("not_owned", "این آیتم در مجموعهٔ تو نیست.", 403)
    return row


@transaction.atomic
def equip(user, slot, grant_id):
    if slot not in EQUIPPABLE:
        raise DomainError("invalid_slot", "جایگاه ظاهر نامعتبر است.")
    locked_wallet(user.pk)
    appearance, _ = UserAppearance.objects.get_or_create(user=user)
    slots = dict(appearance.slots)
    if grant_id is None:
        slots.pop(slot, None)
    else:
        grant = owned(user, grant_id)
        if grant.snapshot["kind"] != slot:
            raise DomainError("invalid_slot", "این آیتم برای این جایگاه نیست.")
        slots[slot] = {"visual": grant.snapshot["visual"], "title": grant.snapshot["title"], "grant_id": grant.pk}
    appearance.slots = slots
    appearance.save(update_fields=["slots"])
    changed_later(user.pk)
    return inventory(user)


def spotlight_active(user_id):
    from .models import VIPSpotlight
    now = timezone.now()
    return ItemUse.objects.filter(user_id=user_id, ends_at__gt=now).exists() or VIPSpotlight.objects.filter(
        subscription__user_id=user_id, subscription__revoked_at__isnull=True,
        subscription__starts_at__lte=now, subscription__ends_at__gt=now, ends_at__gt=now).exists()


@transaction.atomic
def use_item(user, grant_id, key, conversation_id=None, recipient_id=None):
    from apps.chat import services as chat
    from apps.chat.models import Conversation
    key = validate_key(key)
    # Same lock ordering as chat/quota: conversation, then wallets in user-id order.
    conversation = None
    if conversation_id:
        conversation = Conversation.objects.select_for_update().filter(pk=conversation_id).first()
        if not conversation:
            raise DomainError("not_found", "گفتگو پیدا نشد.", 404)
        for uid in sorted(set(chat.participant_user_ids(conversation.pk)) | {user.pk}):
            locked_wallet(uid)
    else:
        locked_wallet(user.pk)
    existing = ItemUse.objects.select_related("message").filter(user=user, idempotency_key=key).first()
    if existing:
        if existing.grant_id != grant_id or existing.recipient_id != recipient_id or (str(existing.message.conversation_id) if existing.message else None) != (str(conversation_id) if conversation_id else None):
            raise DomainError("idempotency_conflict", "شناسه برای اقدام دیگری استفاده شده است.", 409)
        return existing
    # A lost response can be retried after the sender closed or left the chat.
    # Replays are safe because the key is bound to the original user, grant,
    # recipient and conversation above; a new action still requires active
    # membership below.
    if conversation is not None:
        chat.active_participant(user, conversation.pk)
    grant = owned(user, grant_id)
    data, now = grant.snapshot, timezone.now()
    kind = data["kind"]
    if kind not in {"SPOTLIGHT", "GIFT", "STICKER"}:
        raise DomainError("invalid_item", "این آیتم از این قسمت استفاده نمی‌شود.")
    if kind in CONSUMABLE and grant.remaining < 1:
        raise DomainError("item_empty", "موجودی این آیتم تمام شده است.", 409)
    if kind == "SPOTLIGHT":
        if conversation_id or recipient_id:
            raise DomainError("invalid_target", "Spotlight فقط برای خودت فعال می‌شود.")
        if user.is_ai or not user.is_active or not user.is_onboarded:
            raise DomainError("profile_incomplete", "اول پروفایلت را کامل کن.", 409)
        if spotlight_active(user.pk):
            raise DomainError("spotlight_active", "Spotlight قبلی هنوز فعال است.", 409)
        use = ItemUse.objects.create(user=user, grant=grant, idempotency_key=key,
                                    ends_at=now + timedelta(minutes=data["spotlight_minutes"]))
    else:
        if not conversation:
            raise DomainError("conversation_required", "گفتگو را انتخاب کن.")
        if kind == "STICKER" and recipient_id is not None:
            raise DomainError("invalid_target", "استیکر گیرندهٔ جدا ندارد.")
        if kind == "GIFT":
            from apps.users.models import User
            receiver = User.objects.filter(pk=recipient_id, is_active=True, is_ai=False).first()
            if not receiver or receiver.pk == user.pk or user.is_ai:
                raise DomainError("invalid_recipient", "گیرندهٔ هدیه معتبر نیست.", 403)
            chat.active_participant(receiver, conversation.pk)
        message, _ = chat.post_message(conversation=conversation, sender=user, body=data["title"],
            message_type="ITEM",
            meta={"item": {"kind": kind, "visual": data["visual"], "title": data["title"], "recipient_id": recipient_id,
                           "recipient_name": receiver.display_name if kind == "GIFT" else None}})
        use = ItemUse.objects.create(user=user, grant=grant, idempotency_key=key, recipient_id=recipient_id, message=message)
    if kind in CONSUMABLE:
        grant.remaining -= 1
        grant.save(update_fields=["remaining"])
    changed_later(user.pk)
    return use


def gift_summary(user):
    rows = list(ItemUse.objects.filter(recipient=user).values("grant__snapshot__visual", "grant__snapshot__title").annotate(count=Count("pk")).order_by("-count")[:12])
    return [{"visual": r["grant__snapshot__visual"], "title": r["grant__snapshot__title"], "count": r["count"]} for r in rows]


def leaders(viewer):
    from apps.users.models import User
    from apps.users.payloads import person_payload
    from .vip import hydrate
    now = timezone.now()
    since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    users = list(User.objects.filter(is_active=True, is_ai=False, received_gifts__created_at__gte=since)
        .exclude(pk__in=viewer.blocks_made.values("blocked_id")).exclude(pk__in=viewer.blocks_received.values("blocker_id"))
        .annotate(gift_count=Count("received_gifts")).order_by("-gift_count", "pk")[:20])
    return [{"user": person_payload(u), "gifts": u.gift_count} for u in hydrate(users)]
