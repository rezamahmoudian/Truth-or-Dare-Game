from django.db import migrations, models


def simplify_default_bios(apps, schema_editor):
    Persona = apps.get_model("ai_players", "Persona")
    User = apps.get_model("users", "User")
    alias = schema_editor.connection.alias
    bios = [
        "عاشق خنده، موسیقی و سؤال‌های غیرمنتظره.",
        "آرام، کتاب‌دوست و طرفدار گفتگوهای عمیق.",
        "پرانرژی، رقابت‌دوست و اهل چالش‌های خلاقانه.",
    ]
    for bio in bios:
        for persona in Persona.objects.using(alias).filter(bio="شخصیت داستانی AI؛ " + bio):
            Persona.objects.using(alias).filter(pk=persona.pk).update(bio=bio)
            User.objects.using(alias).filter(pk=persona.user_id, bio=persona.bio).update(bio=bio)


class Migration(migrations.Migration):
    dependencies = [("ai_players", "0005_remove_verbose_welcome")]
    operations = [
        migrations.AddField(model_name="airequest", name="deliver_at",
                            field=models.DateTimeField(blank=True, null=True, db_index=True)),
        migrations.AddField(model_name="airequest", name="delivery_payload",
                            field=models.JSONField(blank=True, default=dict)),
        migrations.RunPython(simplify_default_bios, migrations.RunPython.noop),
    ]
