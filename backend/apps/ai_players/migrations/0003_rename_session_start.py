from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [("ai_players", "0002_aiconversation_expires_at")]
    operations = [
        migrations.RenameField("aiconversation", "consented_at", "started_at"),
        migrations.AlterField("aiconversation", "started_at", models.DateTimeField("زمان شروع", default=timezone.now)),
    ]
