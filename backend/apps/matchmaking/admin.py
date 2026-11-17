from django.contrib import admin

from apps.matchmaking.models import MatchMode, MatchTicket


@admin.register(MatchMode)
class MatchModeAdmin(admin.ModelAdmin):
    """Adding a mode here is the whole deployment process for a new mode."""

    list_display = (
        "key",
        "title",
        "size_min",
        "size_max",
        "target_gender",
        "daily_limit",
        "is_featured",
        "is_active",
        "is_ai",
        "sort_order",
    )
    list_editable = ("is_featured", "is_active", "sort_order")
    list_filter = ("is_active", "is_featured", "target_gender")
    search_fields = ("key", "title")


@admin.register(MatchTicket)
class MatchTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "mode", "state", "uses_credit", "quota_consumed_at", "created_at")
    list_filter = ("state", "uses_credit", "mode")
    raw_id_fields = ("user", "conversation")
    readonly_fields = tuple(field.name for field in MatchTicket._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
