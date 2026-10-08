from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.game.models import Prompt, PromptReviewStatus
from apps.game.review_prompt_bank import entries


class ReviewImportTests(TestCase):
    def test_pack_counts_and_all_new_entries_require_review(self):
        rows = list(entries())
        self.assertEqual(len(rows), 225)
        self.assertEqual(sum("تألیف تازه" in r["review_note"] for r in rows), 40)
        call_command("import_review_prompts", stdout=StringIO())
        self.assertEqual(Prompt.objects.count(), 225)
        self.assertFalse(Prompt.objects.exclude(review_status=PromptReviewStatus.PENDING).exists())
        self.assertFalse(Prompt.objects.filter(reviewed_at__isnull=False).exists())
        self.assertEqual(Prompt.objects.filter(category="BOLD", intensity=3).count(), 86)

    def test_dry_run_and_repeat_preserve_existing_moderation_and_spelling(self):
        row = next(entries())
        original = Prompt.objects.create(
            text=row["text"].replace("ی", "ي").replace("\u200c", " "),
            type="TRUTH", category="DEEP", review_status="REJECTED", is_active=False,
            review_note="Keep moderator decision",
        )
        call_command("import_review_prompts", dry_run=True, stdout=StringIO())
        self.assertEqual(Prompt.objects.count(), 1)
        call_command("import_review_prompts", stdout=StringIO())
        call_command("import_review_prompts", stdout=StringIO())
        self.assertEqual(Prompt.objects.count(), 225)
        original.refresh_from_db()
        self.assertEqual(original.review_status, "REJECTED")
        self.assertEqual(original.category, "DEEP")
        self.assertFalse(original.is_active)
        self.assertEqual(original.review_note, "Keep moderator decision")
