# Generated manually for the prompt suggestion and moderation workflow.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0004_remove_gamesession_rounds"),
    ]

    operations = [
        migrations.AddField(
            model_name="prompt",
            name="review_note",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="prompt",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "در انتظار بررسی"),
                    ("APPROVED", "تأییدشده"),
                    ("REJECTED", "ردشده"),
                ],
                db_index=True,
                default="PENDING",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="prompt",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="prompt",
            name="source",
            field=models.CharField(
                choices=[("SEED", "پیش‌فرض"), ("USER", "پیشنهاد کاربر")],
                db_index=True,
                default="SEED",
                max_length=4,
            ),
        ),
        migrations.AddField(
            model_name="prompt",
            name="submitted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prompt_suggestions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="prompt",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_prompts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="prompt",
            index=models.Index(
                fields=["review_status", "source", "created_at"],
                name="game_prompt_review_9f5a6d_idx",
            ),
        ),
    ]
