from django.contrib import admin

from apps.moderation.models import BannedWord


@admin.register(BannedWord)
class BannedWordAdmin(admin.ModelAdmin):
    """Where the word filter is actually maintained.

    Editable severity and the on/off switch in the list view on purpose: the
    common moderation action is downgrading a word that turned out to fire on
    innocent messages, and that should take one click, not a form.
    """

    list_display = ("word", "severity", "whole_word", "is_active", "note")
    list_editable = ("severity", "whole_word", "is_active")
    list_filter = ("severity", "is_active", "whole_word")
    search_fields = ("word", "note")
