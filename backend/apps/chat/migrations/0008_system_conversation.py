from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0007_conversation_transcript_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="is_system",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddConstraint(
            model_name="conversation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_system", True), ("owner__isnull", False)),
                fields=("owner",),
                name="unique_system_conversation_owner",
            ),
        ),
    ]
