import uuid
from .item_models import DigitalItem, InventoryGrant, ItemUse, UserAppearance, RewardSession  # noqa: F401

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ProductKind(models.TextChoices):
    CREDITS = "CREDITS", "بسته درخواست"
    VIP = "VIP", "عضویت VIP"
    ITEM = "ITEM", "آیتم و بستهٔ سؤال"


class Product(models.Model):
    key = models.SlugField(max_length=64, unique=True)
    title = models.CharField("نام", max_length=120)
    description = models.TextField("توضیح", blank=True)
    kind = models.CharField(max_length=10, choices=ProductKind.choices)
    credits = models.PositiveIntegerField("تعداد درخواست", validators=[MaxValueValidator(1000000)])
    duration_days = models.PositiveSmallIntegerField("روزهای عضویت", default=0)
    credit_validity_days = models.PositiveSmallIntegerField("اعتبار بسته به روز؛ خالی یعنی بدون انقضا", null=True, blank=True, validators=[MinValueValidator(1)])
    benefits = models.JSONField("مزایای نمایشی", default=dict, blank=True)
    is_active = models.BooleanField("فعال", default=False)
    sort_order = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "محصول"
        verbose_name_plural = "محصول‌ها"
        constraints = [
            models.CheckConstraint(condition=Q(credits__lte=1000000), name="billing_product_credit_cap"),
            models.CheckConstraint(condition=(Q(kind="CREDITS", credits__gt=0, duration_days=0) | Q(kind="VIP", duration_days__gt=0, credit_validity_days__isnull=True) | Q(kind="ITEM", credits=0, duration_days=0, credit_validity_days__isnull=True)), name="billing_product_kind_shape"),
            models.CheckConstraint(condition=Q(credit_validity_days__isnull=True) | Q(credit_validity_days__gt=0), name="billing_credit_validity_positive"),
        ]

    def clean(self):
        if not isinstance(self.benefits, dict):
            raise ValidationError({"benefits": "مزایا باید یک شیء JSON باشد."})
        if self.kind == ProductKind.VIP:
            from .vip import DEFAULT_BENEFITS, LIMITS
            for key, value in self.benefits.items():
                if key in LIMITS:
                    low, high = LIMITS[key]
                    if type(value) is not int or not low <= value <= high:
                        raise ValidationError({"benefits": f"{key}: عدد صحیح بین {low} و {high} لازم است."})
                elif key in DEFAULT_BENEFITS and type(value) is not bool:
                    raise ValidationError({"benefits": f"{key}: فقط true یا false مجاز است."})

    def __str__(self):
        return self.title


class Currency(models.TextChoices):
    IRR = "IRR", "ریال"


class ProductOffer(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="offers")
    key = models.SlugField(max_length=80, unique=True)
    channel = models.CharField(max_length=16, default="web")
    amount = models.PositiveBigIntegerField("مبلغ نهایی به ریال", validators=[MinValueValidator(1), MaxValueValidator(10**12)])
    original_amount = models.PositiveBigIntegerField("قبل از تخفیف به ریال", null=True, blank=True)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.IRR)
    is_active = models.BooleanField(default=False)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "پیشنهاد فروش"
        verbose_name_plural = "قیمت‌ها و پیشنهادهای فروش"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0, amount__lte=10**12, currency="IRR"), name="billing_offer_valid_money"),
            models.CheckConstraint(condition=Q(original_amount__isnull=True) | Q(original_amount__gte=F("amount")), name="billing_offer_discount"),
            models.CheckConstraint(condition=Q(ends_at__isnull=True) | Q(ends_at__gt=F("starts_at")), name="billing_offer_date_range"),
        ]

    def __str__(self):
        return f"{self.key} · {self.amount} IRR"


class Wallet(models.Model):
    """Request-credit wallet; never a cash balance. Lock before financial writes."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="credit_wallet")
    balance = models.PositiveBigIntegerField(default=0)
    reserved = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "کیف اعتبار"
        verbose_name_plural = "کیف‌های اعتبار"
        permissions = [("adjust_wallet", "Can grant request credits with an audit reason"),
                       ("debit_wallet", "Can remove unreserved credits with an audit reason")]
        constraints = [models.CheckConstraint(condition=Q(reserved__lte=F("balance")), name="billing_wallet_covered_reserve")]

    @property
    def available(self):
        return self.balance - self.reserved


class OrderStatus(models.TextChoices):
    PENDING = "PENDING", "در انتظار پرداخت"
    PAID = "PAID", "پرداخت تأیید شده؛ در انتظار تحویل"
    FULFILLED = "FULFILLED", "تحویل داده شده"


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="billing_orders")
    offer = models.ForeignKey(ProductOffer, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=100)
    product_snapshot = models.JSONField()
    amount = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.IRR)
    status = models.CharField(max_length=12, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        permissions = [("view_finance_dashboard", "Can view financial dashboard and reports"),
                       ("retry_delivery", "Can retry verified order delivery")]
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="billing_order_idempotent"),
            models.CheckConstraint(condition=Q(amount__gt=0, currency="IRR"), name="billing_order_valid_money"),
            models.CheckConstraint(condition=Q(expires_at__gt=F("created_at")), name="billing_order_date_range"),
            models.CheckConstraint(condition=(Q(status="PENDING", paid_at__isnull=True, fulfilled_at__isnull=True) | Q(status="PAID", paid_at__isnull=False, fulfilled_at__isnull=True) | Q(status="FULFILLED", paid_at__isnull=False, fulfilled_at__isnull=False)), name="billing_order_status_dates"),
        ]

    def __str__(self):
        return str(self.pk)


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "در انتظار نتیجه"
    VERIFIED = "VERIFIED", "تأیید شده"
    FAILED = "FAILED", "ناموفق"


class PaymentAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payment_attempts")
    idempotency_key = models.CharField(max_length=100)
    provider = models.SlugField(max_length=40)
    provider_reference = models.CharField(max_length=200, null=True, blank=True)
    transaction_id = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    verified_amount = models.PositiveBigIntegerField(null=True, blank=True)
    verified_currency = models.CharField(max_length=3, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    # A redacted provider code, never raw card/account data or credentials.
    result_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تلاش پرداخت"
        verbose_name_plural = "تلاش‌های پرداخت"
        constraints = [
            models.UniqueConstraint(fields=["order", "idempotency_key"], name="billing_payment_idempotent"),
            models.UniqueConstraint(fields=["provider", "provider_reference"], name="billing_provider_reference_unique"),
            models.UniqueConstraint(fields=["provider", "transaction_id"], name="billing_provider_transaction_unique"),
            models.UniqueConstraint(fields=["order"], condition=Q(status="PENDING"), name="billing_one_pending_payment"),
            models.UniqueConstraint(fields=["order"], condition=Q(status="VERIFIED"), name="billing_one_verified_payment"),
            models.CheckConstraint(condition=((Q(status="VERIFIED", verified_at__isnull=False, transaction_id__isnull=False, verified_amount__isnull=False, verified_amount__gt=0, verified_currency="IRR") & ~Q(transaction_id="")) | Q(status__in=["PENDING", "FAILED"], verified_at__isnull=True, transaction_id__isnull=True, verified_amount__isnull=True, verified_currency="")), name="billing_payment_verification_shape"),
        ]


class PaymentCheckout(models.Model):
    """Durable orchestration state, separate from immutable payment evidence."""
    attempt = models.OneToOneField(PaymentAttempt, primary_key=True, on_delete=models.PROTECT, related_name="checkout")
    callback_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    redirect_url = models.URLField(max_length=2000, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(default=timezone.now, null=True, blank=True, db_index=True)
    checks = models.PositiveIntegerField(default=0)
    needs_review = models.BooleanField(default=False)
    last_code = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [("review_payments", "Can resume bank verification for reviewed payments")]
        verbose_name = "پیگیری درگاه"
        verbose_name_plural = "پیگیری پرداخت‌های درگاه"


class VIPSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vip_periods")
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="vip_period")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    benefits = models.JSONField(default=dict)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [("revoke_vip", "Can revoke VIP and its unused credits")]
        verbose_name = "دوره VIP"
        verbose_name_plural = "دوره‌های VIP"
        indexes = [models.Index(fields=["user", "ends_at"])]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="billing_vip_date_range")]


class GrantSource(models.TextChoices):
    PURCHASE = "PURCHASE", "خرید بسته"
    VIP = "VIP", "اعتبار دوره VIP"
    ADMIN = "ADMIN", "اعطای پشتیبانی"


class VIPSpotlight(models.Model):
    subscription = models.ForeignKey(VIPSubscription, on_delete=models.PROTECT, related_name="spotlights")
    idempotency_key = models.CharField(max_length=100)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "Spotlight"
        verbose_name_plural = "نوبت‌های Spotlight"
        constraints = [
            models.UniqueConstraint(fields=["subscription", "idempotency_key"], name="billing_spotlight_idempotent"),
            models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="billing_spotlight_dates"),
        ]


class GrantStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "دوره آینده"
    ACTIVE = "ACTIVE", "فعال"
    EXPIRED = "EXPIRED", "منقضی"
    REVOKED = "REVOKED", "لغو شده"


class Entitlement(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="entitlements")
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="entitlement", null=True, blank=True)
    source = models.CharField(max_length=10, choices=GrantSource.choices)
    amount = models.PositiveIntegerField()
    remaining = models.PositiveIntegerField()
    reserved = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=GrantStatus.choices, default=GrantStatus.SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "اعتبار اختصاص‌یافته"
        verbose_name_plural = "اعتبارهای اختصاص‌یافته"
        indexes = [models.Index(fields=["wallet", "status", "expires_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0, remaining__lte=F("amount"), reserved__lte=F("remaining")), name="billing_grant_amounts"),
            models.CheckConstraint(condition=Q(expires_at__isnull=True) | Q(expires_at__gt=F("starts_at")), name="billing_grant_date_range"),
            models.CheckConstraint(condition=Q(status="ACTIVE") | Q(status__in=["SCHEDULED", "EXPIRED", "REVOKED"], remaining=0, reserved=0), name="billing_grant_status_amounts"),
            models.CheckConstraint(condition=Q(source="ADMIN", order__isnull=True) | Q(source__in=["PURCHASE", "VIP"], order__isnull=False), name="billing_grant_source_order"),
        ]


class ReservationStatus(models.TextChoices):
    HELD = "HELD", "رزرو شده"
    CONSUMED = "CONSUMED", "مصرف شده"
    RELEASED = "RELEASED", "آزاد شده"
    EXPIRED = "EXPIRED", "منقضی"


class MatchCreditReservation(models.Model):
    """One request costs one credit from one grant. No matcher hooks in phase two."""
    ticket = models.OneToOneField("matchmaking.MatchTicket", on_delete=models.PROTECT, related_name="credit_reservation")
    entitlement = models.ForeignKey(Entitlement, on_delete=models.PROTECT, related_name="reservations")
    status = models.CharField(max_length=10, choices=ReservationStatus.choices, default=ReservationStatus.HELD)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=240, blank=True)

    class Meta:
        verbose_name = "رزرو اعتبار مچ"
        verbose_name_plural = "رزروهای اعتبار مچ"
        constraints = [models.CheckConstraint(condition=Q(status="HELD", closed_at__isnull=True) | Q(status__in=["CONSUMED", "RELEASED", "EXPIRED"], closed_at__isnull=False), name="billing_reservation_status_date")]


class LedgerKind(models.TextChoices):
    GRANT = "GRANT", "اعطای اعتبار"
    RESERVE = "RESERVE", "رزرو اعتبار"
    RELEASE = "RELEASE", "آزادسازی رزرو"
    CONSUME = "CONSUME", "مصرف"
    EXPIRE = "EXPIRE", "انقضای اعتبار"
    ADJUST = "ADJUST", "اصلاح اعتبار توسط پشتیبانی"


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("دفتر تراکنش‌ها قابل ویرایش نیست.")

    def delete(self):
        raise ValidationError("دفتر تراکنش‌ها قابل حذف نیست.")


class WalletLedger(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="ledger")
    entitlement = models.ForeignKey(Entitlement, on_delete=models.PROTECT)
    reservation = models.ForeignKey(MatchCreditReservation, on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=10, choices=LedgerKind.choices)
    idempotency_key = models.CharField(max_length=160)
    delta = models.BigIntegerField()
    reserved_delta = models.BigIntegerField(default=0)
    balance_before = models.PositiveBigIntegerField()
    balance_after = models.PositiveBigIntegerField()
    reserved_before = models.PositiveBigIntegerField()
    reserved_after = models.PositiveBigIntegerField()
    reason = models.CharField(max_length=240)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="billing_adjustments")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ("-id",)
        verbose_name = "ردیف دفتر تراکنش"
        verbose_name_plural = "دفتر تراکنش‌ها"
        constraints = [
            models.UniqueConstraint(fields=["wallet", "idempotency_key"], name="billing_ledger_idempotent"),
            models.CheckConstraint(condition=Q(balance_after=F("balance_before") + F("delta")), name="billing_ledger_balance_equation"),
            models.CheckConstraint(condition=Q(reserved_after=F("reserved_before") + F("reserved_delta")), name="billing_ledger_reserve_equation"),
            models.CheckConstraint(condition=Q(reserved_after__lte=F("balance_after"), reserved_before__lte=F("balance_before")), name="billing_ledger_covered_reserve"),
            models.CheckConstraint(condition=(Q(kind="GRANT", delta__gt=0, reserved_delta=0) | Q(kind="RESERVE", delta=0, reserved_delta=1) | Q(kind="RELEASE", delta=0, reserved_delta=-1) | Q(kind="CONSUME", delta=-1, reserved_delta=-1) | Q(kind__in=["EXPIRE", "ADJUST"], delta__lt=0, reserved_delta=0)), name="billing_ledger_operation_shape"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("برای اصلاح موجودی، تراکنش جبرانی ثبت کنید.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("دفتر تراکنش‌ها قابل حذف نیست.")


class SupportOperation(models.Model):
    """Immutable receipt for a successful, idempotent support operation."""
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="support_operations")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=100)
    action = models.CharField(max_length=24)
    target = models.CharField(max_length=150)
    reason = models.CharField(max_length=240)
    parameters = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ("-id",)
        verbose_name = "عملیات پشتیبانی مالی"
        verbose_name_plural = "سابقه عملیات پشتیبانی مالی"
        constraints = [models.UniqueConstraint(fields=["wallet", "idempotency_key"], name="billing_support_idempotent")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("سابقه عملیات مالی قابل ویرایش نیست.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("سابقه عملیات مالی قابل حذف نیست.")
