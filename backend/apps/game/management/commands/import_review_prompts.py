"""Import the curated review pack without overriding moderation decisions."""

import unicodedata
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.game.models import Category, Prompt, PromptReviewStatus, PromptSource, PromptType
from apps.game.review_prompt_bank import entries


def text_key(text):
    text = unicodedata.normalize("NFKC", text).translate(str.maketrans("يك", "یک"))
    return "".join(text.replace("\u200c", " ").split())


class Command(BaseCommand):
    help = "Import the October review pack as PENDING. Safe to re-run; existing rows stay unchanged."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Validate and report without saving.")

    @transaction.atomic
    def handle(self, *args, **options):
        rows = list(entries())
        for row in rows:
            if (row["category"] not in Category.values or row["type"] not in PromptType.values
                    or row["intensity"] not in (1, 2, 3) or len(row["review_note"]) > 300):
                raise CommandError(f"Invalid prompt metadata: {row['text']}")
        existing = {text_key(text) for text in Prompt.objects.values_list("text", flat=True)}
        counts = Counter()
        skipped = 0
        for row in rows:
            key = text_key(row["text"])
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            defaults = {k: v for k, v in row.items() if k != "text"}
            if row["type"] == PromptType.DARE and any(
                phrase in row["text"] for phrase in ("تماس چشمی", "برقص")
            ):
                defaults["review_note"] += " · بررسی امکان اجرای آنلاین پیش از تأیید"
            if not options["dry_run"]:
                _, created = Prompt.objects.get_or_create(
                    text=row["text"],
                    defaults={
                        **defaults,
                        "review_status": PromptReviewStatus.PENDING,
                        "source": PromptSource.SEED,
                        "is_active": True,
                        "min_players": 2,
                    },
                )
                if not created:
                    skipped += 1
                    continue
            counts[(row["category"], row["type"])] += 1
        mode = "Would add" if options["dry_run"] else "Added"
        self.stdout.write(f"{mode} {sum(counts.values())} PENDING prompts; skipped {skipped} existing/duplicate; pack {len(rows)}.")
        for (category, prompt_type), count in sorted(counts.items()):
            self.stdout.write(f"  {category}/{prompt_type}: {count}")
