from django.core.management.base import BaseCommand

from apps.moderation.models import BannedWord, Severity

B, M = Severity.BLOCK, Severity.MASK

# A starting list, not a finished one. No word list is ever complete, and this
# one is deliberately small and conservative: every entry here is something
# nobody types by accident, because a filter that fires on ordinary words gets
# switched off by whoever is running the product.
#
# The moderator's job from here is to add terms as they appear, through the
# admin. Inflections are listed separately rather than matched as substrings —
# "کون" with whole-word matching leaves "اکنون" alone, which is the point.
#
# (severity, word, whole_word)
WORDS: list[tuple[str, str, bool]] = [
    # --- refused outright: sexual and family-directed abuse ---------------
    (B, "کیر", True),
    (B, "کیری", True),
    (B, "کس", True),
    (B, "کسکش", True),
    (B, "کص", True),
    (B, "کون", True),
    (B, "کونی", True),
    (B, "جنده", True),
    (B, "جاکش", True),
    (B, "مادرجنده", True),
    (B, "خارکسده", True),
    (B, "خارکصده", True),
    (B, "حرومزاده", True),
    (B, "حرامزاده", True),
    (B, "بیناموس", True),
    (B, "بی ناموس", True),
    (B, "دیوث", True),
    (B, "قرمساق", True),
    (B, "پدرسگ", True),
    (B, "گاییدم", True),
    (B, "گایید", True),
    (B, "بگا", True),
    (B, "ساک زدن", True),
    (B, "fuck", False),
    (B, "bitch", True),
    (B, "whore", True),
    (B, "pussy", True),
    # --- masked: crude, but not abuse ------------------------------------
    (M, "کثافت", True),
    (M, "عوضی", True),
    (M, "بیشعور", True),
    (M, "بی شعور", True),
    (M, "احمق", True),
    (M, "گوه", True),
    (M, "گه", True),
    (M, "خفه شو", True),
    (M, "زنیکه", True),
    (M, "مرتیکه", True),
    (M, "نکبت", True),
    (M, "shit", True),
    (M, "asshole", True),
]


class Command(BaseCommand):
    help = "Load the starter word filter. Safe to re-run; edits are preserved."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--update",
            action="store_true",
            help="Also reset severity on words that already exist.",
        )

    def handle(self, *args, **options) -> None:
        created = updated = 0
        for severity, word, whole_word in WORDS:
            defaults = {"severity": severity, "whole_word": whole_word}
            row, was_created = BannedWord.objects.get_or_create(
                word=word, defaults=defaults
            )
            if was_created:
                created += 1
            elif options["update"]:
                # A moderator may have deliberately downgraded or disabled a
                # word; that decision is not overwritten unless asked for.
                for field, value in defaults.items():
                    setattr(row, field, value)
                row.save(update_fields=list(defaults))
                updated += 1

        total = BannedWord.objects.filter(is_active=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} added, {updated} updated — {total} active words"
            )
        )
