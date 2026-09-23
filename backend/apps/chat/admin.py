from django.contrib import admin

from apps.chat.models import Conversation, Message, Participant, Reaction


class ParticipantInline(admin.TabularInline):
    model = Participant
    extra = 0
    raw_id_fields = ("user",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "status", "code", "last_message_at")
    list_filter = ("type", "status")
    search_fields = ("code", "id")
    inlines = [ParticipantInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "type", "created_at", "is_deleted")
    list_filter = ("type", "is_deleted")
    search_fields = ("body",)
    raw_id_fields = ("conversation", "sender", "reply_to")


admin.site.register(Reaction)
