from django.core.management.base import BaseCommand

from apps.matchmaking.models import MatchMode

# Ordering and sizing here are a product decision, not decoration.
#
# These products skew heavily male, so demand for "play with a girl" vastly
# exceeds supply while the mirror queue fills instantly. Left alone, the
# filtered queue starves and a first-time user concludes the app is dead. Three
# of the four levers are in this table:
#
#   * quick and group are featured, so traffic flows to queues that fill
#   * the scarce-direction mode is capped per day, which reins in demand
#   * every mode widens after 20 seconds and says so
#
# The fourth lever — priority for the under-supplied side — is in the matcher.
MODES = [
    {
        "key": "quick",
        "title": "شروع سریع",
        "subtitle": "با یک نفر تصادفی",
        "emoji": "⚡",
        "accent": "brand",
        "size_min": 2,
        "size_max": 2,
        "is_featured": True,
        "sort_order": 1,
    },
    {
        "key": "group",
        "title": "بازی گروهی",
        "subtitle": "۳ تا ۶ نفر",
        "emoji": "👥",
        "accent": "ok",
        "size_min": 3,
        "size_max": 6,
        "is_featured": True,
        "sort_order": 2,
    },
    {
        "key": "girls",
        "title": "بازی با دختر",
        "subtitle": "روزی ۳ بار",
        "emoji": "🌸",
        "accent": "pink",
        "size_min": 2,
        "size_max": 2,
        "target_gender": "F",
        "daily_limit": 3,
        "sort_order": 3,
    },
    {
        "key": "boys",
        "title": "بازی با پسر",
        "subtitle": "روزی ۳ بار",
        "emoji": "🎧",
        "accent": "blue",
        "size_min": 2,
        "size_max": 2,
        "target_gender": "M",
        "daily_limit": 3,
        "sort_order": 4,
    },
    {
        "key": "deep",
        "title": "گفتگوی عمیق",
        "subtitle": "سؤال‌های جدی‌تر",
        "emoji": "🌙",
        "accent": "purple",
        "size_min": 2,
        "size_max": 2,
        "category": "DEEP",
        "max_intensity": 3,
        "sort_order": 5,
    },
]


class Command(BaseCommand):
    help = "Create or refresh the match modes. Safe to re-run."

    def handle(self, *args, **options) -> None:
        created = updated = 0
        for spec in MODES:
            _, was_created = MatchMode.objects.update_or_create(
                key=spec["key"], defaults=spec
            )
            created += was_created
            updated += not was_created

        self.stdout.write(
            self.style.SUCCESS(
                f"{created} created, {updated} updated — "
                f"{MatchMode.objects.filter(is_active=True).count()} active modes"
            )
        )
