from django.core.management.base import BaseCommand

from apps.game.models import Prompt, PromptReviewStatus
from apps.game.prompt_bank import PENDING_PROMPTS, PROMPTS


class Command(BaseCommand):
    help = "Load the starter prompt bank. Safe to re-run; existing prompts are left alone."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--update",
            action="store_true",
            help="Also refresh category/intensity on prompts that already exist.",
        )

    def handle(self, *args, **options) -> None:
        created = updated = 0

        banks = (
            (PROMPTS, PromptReviewStatus.APPROVED, True),
            (PENDING_PROMPTS, PromptReviewStatus.PENDING, False),
        )
        for bank, review_status, is_active in banks:
            for prompt_type, category, intensity, text in bank:
                defaults = {
                    "type": prompt_type,
                    "category": category,
                    "intensity": intensity,
                    "review_status": review_status,
                    "is_active": is_active,
                }
                # Keyed on text so re-running never duplicates, and so a
                # prompt deactivated by a moderator is not silently resurrected.
                prompt, was_created = Prompt.objects.get_or_create(
                    text=text, defaults=defaults
                )
                if was_created:
                    created += 1
                elif options["update"]:
                    # Keep moderator decisions (including deactivation) intact;
                    # --update only refreshes the metadata owned by this bank.
                    for field in ("type", "category", "intensity"):
                        value = defaults[field]
                        setattr(prompt, field, value)
                    prompt.save(update_fields=["type", "category", "intensity"])
                    updated += 1

        total = Prompt.objects.filter(
            is_active=True, review_status=PromptReviewStatus.APPROVED
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} added, {updated} updated — {total} approved active prompts"
            )
        )
