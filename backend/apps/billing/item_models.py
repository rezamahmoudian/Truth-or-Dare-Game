"""Digital goods use their own inventory; request credits remain request credits."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


class ItemKind(models.TextChoices):
    FRAME = "FRAME", "قاب عکس"
    NAME = "NAME", "رنگ نام"
    BADGE = "BADGE", "نشان"
    THEME = "THEME", "تم چت"
    EFFECT = "EFFECT", "افکت پیام"
    STICKER = "STICKER", "استیکر"
    REACTION = "REACTION", "واکنش ویژه"
    SPOTLIGHT = "SPOTLIGHT", "دیده‌شدن بیشتر"
    PACK = "PACK", "بستهٔ سؤال"
    GIFT = "GIFT", "هدیه"


VISUALS = {
    "FRAME": {"aurora", "rose", "ocean"}, "NAME": {"lilac", "mint", "peach"},
    "BADGE": {"star", "spark", "moon"}, "THEME": {"midnight", "forest", "sunset"},
    "EFFECT": {"sparkle", "hearts"}, "STICKER": {"party", "highfive", "wow"},
    "REACTION": {"💎", "🪄", "💫"}, "GIFT": {"rose", "star", "coffee"},
    "SPOTLIGHT": {"spotlight"}, "PACK": {"cards"},
}
EQUIPPABLE = {"FRAME", "NAME", "BADGE", "THEME", "EFFECT"}
CONSUMABLE = {"GIFT", "SPOTLIGHT"}


class DigitalItem(models.Model):
    product = models.OneToOneField("billing.Product", on_delete=models.PROTECT, related_name="item")
    kind = models.CharField(max_length=10, choices=ItemKind.choices)
    visual = models.CharField(max_length=24)
    units = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(100)])
    spotlight_minutes = models.PositiveSmallIntegerField(default=15, validators=[MinValueValidator(1), MaxValueValidator(60)])

    class Meta:
        verbose_name = "آیتم فروشگاه"
        verbose_name_plural = "آیتم‌های فروشگاه"
        constraints = [models.CheckConstraint(condition=Q(units__gte=1, units__lte=100, spotlight_minutes__gte=1, spotlight_minutes__lte=60), name="billing_item_bounds")]

    def clean(self):
        if self.product_id and self.product.kind != "ITEM":
            raise ValidationError("محصول باید از نوع آیتم باشد.")
        if self.visual not in VISUALS.get(self.kind, set()):
            raise ValidationError({"visual": "طرح مجاز: " + ", ".join(sorted(VISUALS.get(self.kind, set())))})
        if self.kind not in CONSUMABLE and self.units != 1:
            raise ValidationError({"units": "آیتم دائمی یک بار به مالکیت کاربر درمی‌آید."})
        if self.pk and InventoryGrant.objects.filter(item=self).exists():
            old = DigitalItem.objects.get(pk=self.pk)
            if old.kind != self.kind or old.visual != self.visual:
                raise ValidationError("نوع و طرح آیتم فروخته‌شده را عوض نکنید؛ آیتم تازه بسازید.")

    def __str__(self):
        return self.product.title


class InventoryGrant(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    item = models.ForeignKey(DigitalItem, on_delete=models.PROTECT)
    order = models.OneToOneField("billing.Order", on_delete=models.PROTECT, null=True, blank=True)
    reward_key = models.CharField(max_length=160, unique=True, null=True, blank=True)
    snapshot = models.JSONField()
    quantity = models.PositiveIntegerField(default=1)
    remaining = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(remaining__lte=F("quantity"), quantity__gt=0), name="billing_inventory_balance"),
                       models.CheckConstraint(condition=Q(order__isnull=False, reward_key__isnull=True) | Q(order__isnull=True, reward_key__isnull=False), name="billing_inventory_source")]
        verbose_name_plural = "موجودی آیتم‌ها"


class ItemUse(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="item_uses")
    grant = models.ForeignKey(InventoryGrant, on_delete=models.PROTECT, related_name="uses")
    idempotency_key = models.CharField(max_length=100)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="received_gifts")
    message = models.OneToOneField("chat.Message", on_delete=models.PROTECT, null=True)
    ends_at = models.DateTimeField(null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "idempotency_key"], name="billing_item_use_idempotent")]
        verbose_name_plural = "مصرف آیتم و هدیه‌ها"


class UserAppearance(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    slots = models.JSONField(default=dict)

    class Meta:
        verbose_name_plural = "ظاهر انتخابی کاربران"


class RewardSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    item = models.ForeignKey(DigitalItem, on_delete=models.PROTECT)
    provider = models.CharField(max_length=40)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    claimed_at = models.DateTimeField(null=True)
    event_id = models.CharField(max_length=100, null=True)
    grant = models.OneToOneField(InventoryGrant, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="billing_reward_event_once")]
        verbose_name_plural = "جلسه‌های تبلیغ جایزه‌ای"
