from django.contrib import admin
from django.urls import path
from django.utils.html import format_html

from .models import Entitlement, MatchCreditReservation, Order, PaymentAttempt, PaymentCheckout, Product, ProductOffer, VIPSubscription, Wallet, WalletLedger, SupportOperation, VIPSpotlight
from .admin_views import dashboard, support_view, support_url
from .models import DigitalItem, InventoryGrant, ItemUse, UserAppearance, RewardSession
from .item_models import VISUALS


@admin.register(DigitalItem)
class DigitalItemAdmin(admin.ModelAdmin):
    list_display = ("product", "kind", "visual", "units", "spotlight_minutes")
    list_filter = ("kind",)
    list_select_related = ("product",)
    search_fields = ("product__title", "product__key")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["visual"].help_text = " | ".join(f"{key}: {', '.join(sorted(values))}" for key, values in VISUALS.items())
        return form

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "kind", "credits", "duration_days", "is_active", "sort_order")
    list_filter = ("kind", "is_active")
    search_fields = ("key", "title")
    readonly_fields = ("created_at", "updated_at")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "benefits" in form.base_fields:
            form.base_fields["benefits"].help_text = 'VIP: gold_profile / vip_badge / exclusive_frame / ad_free: true یا false؛ queue_priority_seconds: 0..120 (پیش‌فرض 60)؛ request_discount_percent: 0..30 (پیش‌فرض 10)؛ spotlight_uses: 0..10 (پیش‌فرض 1)؛ spotlight_minutes: 1..60 (پیش‌فرض 15). تغییرات برای خریدهای بعدی است.'
        return form

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductOffer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("key", "product", "amount", "currency", "channel", "is_active", "starts_at", "ends_at")
    list_filter = ("is_active", "channel", "product__kind")
    list_select_related = ("product",)
    search_fields = ("key", "product__title")
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False


class FinancialReadOnlyAdmin(admin.ModelAdmin):
    """Services alone may change balances, payment evidence and delivery state."""
    actions = None
    change_list_template = "admin/billing/order/change_list.html"
    support_permission = None

    def get_list_display(self, request):
        columns = super().get_list_display(request)
        if self.support_permission and not request.user.has_perm(self.support_permission):
            return tuple(column for column in columns if column != "support_link")
        return columns

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InventoryGrant)
class InventoryAdmin(FinancialReadOnlyAdmin):
    list_display = ("id", "user", "item", "quantity", "remaining", "created_at")
    list_select_related = ("user", "item__product")
    search_fields = ("user__username", "item__product__title")


@admin.register(ItemUse)
class ItemUseAdmin(FinancialReadOnlyAdmin):
    list_display = ("id", "user", "grant", "recipient", "ends_at", "created_at")
    list_select_related = ("user", "recipient", "grant")
    search_fields = ("user__username", "recipient__username", "idempotency_key")


@admin.register(UserAppearance)
class AppearanceAdmin(FinancialReadOnlyAdmin):
    list_display = ("user", "slots")
    list_select_related = ("user",)


@admin.register(RewardSession)
class RewardSessionAdmin(FinancialReadOnlyAdmin):
    list_display = ("id", "user", "provider", "created_at", "expires_at", "claimed_at")
    list_select_related = ("user",)
    search_fields = ("user__username", "event_id")


@admin.register(Order)
class OrderAdmin(FinancialReadOnlyAdmin):
    support_permission = "billing.retry_delivery"
    list_display = ("id", "user", "amount", "currency", "status", "created_at", "support_link")
    list_filter = ("status", "created_at")
    list_select_related = ("user",)
    search_fields = ("=id", "user__username", "idempotency_key")

    @admin.display(description="رسیدگی")
    def support_link(self, obj):
        if obj.status == "PAID":
            return format_html('<a href="{}">تحویل دوباره</a>', support_url("retry_delivery", obj.pk))
        return "—"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("dashboard/", self.admin_site.admin_view(lambda request: dashboard(self.admin_site, request)), name="billing_order_dashboard"),
            path("support/", self.admin_site.admin_view(lambda request: support_view(self.admin_site, request)), name="billing_order_support"),
        ]
        return custom + urls


@admin.register(PaymentAttempt)
class PaymentAdmin(FinancialReadOnlyAdmin):
    list_display = ("id", "order", "provider", "status", "verified_amount", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("=id", "provider_reference", "transaction_id")


@admin.register(PaymentCheckout)
class CheckoutAdmin(FinancialReadOnlyAdmin):
    support_permission = "billing.review_payments"
    list_display = ("attempt", "last_code", "needs_review", "checks", "next_check_at", "updated_at", "support_link")
    list_filter = ("needs_review", "last_code")
    list_select_related = ("attempt__order__user",)
    search_fields = ("=attempt__id", "=attempt__order__id", "attempt__order__user__username", "attempt__provider_reference")
    exclude = ("callback_key", "redirect_url", "lease_token")

    @admin.display(description="رسیدگی")
    def support_link(self, obj):
        if obj.attempt.status == "PENDING":
            return format_html('<a href="{}">استعلام دوباره</a>', support_url("review_payment", obj.pk))
        return "—"


@admin.register(Wallet)
class WalletAdmin(FinancialReadOnlyAdmin):
    support_permission = "billing.adjust_wallet"
    list_display = ("user", "balance", "reserved", "available", "support_link")
    list_select_related = ("user",)
    search_fields = ("user__username",)

    @admin.display(description="رسیدگی")
    def support_link(self, obj):
        return format_html('<a href="{}">جبران / افزایش اعتبار</a>', support_url("grant", obj.user.username))


@admin.register(WalletLedger)
class LedgerAdmin(FinancialReadOnlyAdmin):
    list_display = ("id", "wallet", "kind", "delta", "reserved_delta", "balance_after", "actor", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("wallet__user__username", "idempotency_key", "reason")
    list_select_related = ("wallet", "actor")


@admin.register(Entitlement)
class EntitlementAdmin(FinancialReadOnlyAdmin):
    support_permission = "billing.debit_wallet"
    list_display = ("id", "wallet", "source", "amount", "remaining", "reserved", "status", "expires_at", "support_link")
    list_select_related = ("wallet__user",)
    list_filter = ("source", "status")
    search_fields = ("wallet__user__username",)

    def lookup_allowed(self, lookup, value, request=None):
        return lookup == "wallet__user__id__exact" or super().lookup_allowed(lookup, value, request)

    @admin.display(description="رسیدگی")
    def support_link(self, obj):
        if obj.status == "ACTIVE" and obj.remaining > obj.reserved:
            return format_html('<a href="{}">اصلاح اعتبار</a>', support_url("debit", obj.pk))
        return "—"


@admin.register(VIPSubscription)
class VIPAdmin(FinancialReadOnlyAdmin):
    support_permission = "billing.revoke_vip"
    list_display = ("id", "user", "starts_at", "ends_at", "revoked_at", "support_link")
    search_fields = ("user__username",)
    list_select_related = ("user",)

    @admin.display(description="رسیدگی")
    def support_link(self, obj):
        if not obj.revoked_at:
            return format_html('<a href="{}">لغو دوره</a>', support_url("revoke_vip", obj.pk))
        return "—"


@admin.register(MatchCreditReservation)
class ReservationAdmin(FinancialReadOnlyAdmin):
    list_display = ("id", "ticket", "entitlement", "status", "created_at", "closed_at")
    list_filter = ("status",)


@admin.register(SupportOperation)
class SupportOperationAdmin(FinancialReadOnlyAdmin):
    list_display = ("id", "action", "target", "wallet", "actor", "reason", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("target", "reason", "wallet__user__username", "actor__username")
    list_select_related = ("wallet__user", "actor")


@admin.register(VIPSpotlight)
class SpotlightAdmin(FinancialReadOnlyAdmin):
    list_display = ("id", "subscription", "starts_at", "ends_at")
    search_fields = ("subscription__user__username",)
    list_select_related = ("subscription",)
