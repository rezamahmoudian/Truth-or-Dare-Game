from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0006_alter_message_type"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="conversation",
            options={
                "ordering": ("-last_message_at", "-created_at"),
                "indexes": [models.Index(fields=["type", "status"], name="chat_conver_type_241fa0_idx")],
                "permissions": [
                    ("view_chat_transcript", "Can view complete chat transcripts"),
                    ("view_chat_transcript_media", "Can view media in chat transcripts"),
                ],
            },
        ),
    ]
