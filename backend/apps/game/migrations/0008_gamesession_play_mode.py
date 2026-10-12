from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("game", "0007_update_category_labels")]
    operations = [migrations.AddField(model_name="gamesession", name="play_mode", field=models.CharField(max_length=12, default="CLASSIC", choices=[("CLASSIC", "جرئت یا حقیقت"), ("DEEP_TALK", "گفت‌وگوی عمیق")]))]
