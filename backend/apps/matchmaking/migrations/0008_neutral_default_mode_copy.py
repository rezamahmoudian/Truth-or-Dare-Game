from django.db import migrations


def update_default_copy(apps, schema_editor):
    modes = apps.get_model("matchmaking", "MatchMode").objects.using(schema_editor.connection.alias)
    # Update only the bundled copy; preserve names and settings edited by admins.
    modes.filter(key="ai-girls", is_ai=True, title="هم‌بازی هوش مصنوعی").update(title="هم‌بازی تازه")
    modes.filter(key="ai-girls", is_ai=True, subtitle="سه شخصیت دختر داستانی، سه حال‌وهوای متفاوت").update(
        subtitle="یه هم‌بازی تازه، یه حال‌وهوای متفاوت"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("matchmaking", "0007_matchticket_funding_expires_at_and_more"),
    ]

    operations = [migrations.RunPython(update_default_copy, migrations.RunPython.noop)]
