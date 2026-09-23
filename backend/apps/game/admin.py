from django.contrib import admin

from apps.game.models import GameSession, Prompt, Turn


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    """The prompt bank is content, not code — moderators live here.

    Deactivating rather than deleting keeps a prompt out of new games without
    breaking the turns that already referenced it.
    """

    list_display = ("short_text", "type", "category", "intensity", "is_active")
    list_filter = ("type", "category", "intensity", "is_active")
    list_editable = ("is_active",)
    search_fields = ("text",)

    @admin.display(description="متن")
    def short_text(self, obj: Prompt) -> str:
        return obj.text[:70]


class TurnInline(admin.TabularInline):
    model = Turn
    extra = 0
    readonly_fields = ("index", "player", "status", "choice", "prompt", "version")


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "status", "turn_index", "rounds", "started_at")
    list_filter = ("status", "category")
    raw_id_fields = ("conversation", "started_by")
    inlines = [TurnInline]
