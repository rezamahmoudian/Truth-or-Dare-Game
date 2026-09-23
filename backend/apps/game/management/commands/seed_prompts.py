from django.core.management.base import BaseCommand

from apps.game.models import Prompt
from apps.game.prompt_bank import PROMPTS


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

        for prompt_type, category, intensity, text in PROMPTS:
            defaults = {
                "type": prompt_type,
                "category": category,
                "intensity": intensity,
            }
            # Keyed on text so re-running never duplicates, and so a prompt
            # deactivated by a moderator is not silently resurrected.
            prompt, was_created = Prompt.objects.get_or_create(
                text=text, defaults=defaults
            )
            if was_created:
                created += 1
            elif options["update"]:
                for field, value in defaults.items():
                    setattr(prompt, field, value)
                prompt.save(update_fields=list(defaults))
                updated += 1

        total = Prompt.objects.filter(is_active=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} added, {updated} updated — {total} active prompts"
            )
        )
