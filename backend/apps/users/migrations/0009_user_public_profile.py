from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0008_user_profile_photo")]
    operations = [
        migrations.AddField(model_name="user", name="city", field=models.CharField("شهر", max_length=64, blank=True)),
        migrations.AddField(model_name="user", name="interests", field=models.JSONField("علایق", default=list, blank=True)),
    ]
