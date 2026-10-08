from django.db import migrations


def remove_errors(apps, schema_editor):
    Message = apps.get_model("chat", "Message")
    Conversation = apps.get_model("chat", "Conversation")
    alias = schema_editor.connection.alias
    errors = Message.objects.using(alias).filter(
        type="SYSTEM", sender_id__isnull=True, meta__has_key="ai_error",
    )
    affected = list(errors.values_list("conversation_id", flat=True).distinct())
    errors.delete()
    for conversation_id in affected:
        last = Message.objects.using(alias).filter(conversation_id=conversation_id).order_by("-id").first()
        preview = ""
        if last and not last.is_deleted:
            preview = last.body[:120] if last.type == "TEXT" else "پیام"
        Conversation.objects.using(alias).filter(pk=conversation_id).update(
            last_message_at=last.created_at if last else None, last_message_preview=preview,
        )


class Migration(migrations.Migration):
    dependencies = [("ai_players", "0006_delayed_replies")]
    operations = [migrations.RunPython(remove_errors, migrations.RunPython.noop)]
