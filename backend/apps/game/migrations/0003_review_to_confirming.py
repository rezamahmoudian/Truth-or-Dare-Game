from django.db import migrations


def forwards(apps, schema_editor):
    """Rename the old REVIEW state.

    A turn used to sit in REVIEW while a timer ran it out. It now sits in
    CONFIRMING until somebody says the player did what was asked, and with the
    timers gone any row left in REVIEW would wait forever.
    """
    Turn = apps.get_model("game", "Turn")
    Turn.objects.filter(status="REVIEW").update(status="CONFIRMING")


def backwards(apps, schema_editor):
    Turn = apps.get_model("game", "Turn")
    Turn.objects.filter(status="CONFIRMING").update(status="REVIEW")


class Migration(migrations.Migration):
    dependencies = [("game", "0002_remove_turn_deadline_at_alter_turn_status_and_more")]

    operations = [migrations.RunPython(forwards, backwards)]
