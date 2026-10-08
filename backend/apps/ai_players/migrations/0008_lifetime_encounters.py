from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_encounters(apps, schema_editor):
    Conversation = apps.get_model("ai_players", "AIConversation")
    Encounter = apps.get_model("ai_players", "AIEncounter")
    alias = schema_editor.connection.alias
    rows = (Conversation.objects.using(alias).values("human_id", "persona_id")
            .annotate(first_matched_at=models.Min("started_at")))
    batch = []
    for row in rows.iterator(chunk_size=1000):
        batch.append(Encounter(**row))
        if len(batch) == 1000:
            Encounter.objects.using(alias).bulk_create(batch, ignore_conflicts=True)
            batch = []
    if batch:
        Encounter.objects.using(alias).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("ai_players", "0007_remove_chat_error_notices"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="AIEncounter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_matched_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("human", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ("persona", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="ai_players.persona")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("human", "persona"), name="ai_encounter_unique_pair")]},
        ),
        migrations.RunPython(backfill_encounters, migrations.RunPython.noop),
    ]
