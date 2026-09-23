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
        "sort_order",
    )
    list_editable = ("is_featured", "is_active", "sort_order")
    list_filter = ("is_active", "is_featured", "target_gender")
    search_fields = ("key", "title")


@admin.register(MatchTicket)
class MatchTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "mode", "state", "widened", "created_at")
    list_filter = ("state", "widened", "mode")
    raw_id_fields = ("user", "conversation")
