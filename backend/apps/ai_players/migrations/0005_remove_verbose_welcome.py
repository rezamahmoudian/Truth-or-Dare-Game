from django.db import migrations


def remove_verbose_welcome(apps, schema_editor):
    Message = apps.get_model("chat", "Message")
    AIConversation = apps.get_model("ai_players", "AIConversation")
    # Remove only the old generated welcome, never player or AI dialogue.
    Message.objects.using(schema_editor.connection.alias).filter(
        conversation_id__in=AIConversation.objects.using(
            schema_editor.connection.alias
        ).values_list("conversation_id", flat=True),
        sender_id__isnull=True,
        type="SYSTEM",
        body__contains="یک شخصیت داستانی هوش مصنوعی است. پیام‌های متنی این گفتگو",
        body__endswith="این شخصیت فقط حقیقت انتخاب می‌کند. هر وقت آماده بودی بازی را شروع کن.",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ai_players", "0004_alter_aiconversation_expires_at_aisettings"),
    ]

    operations = [migrations.RunPython(remove_verbose_welcome, migrations.RunPython.noop)]
