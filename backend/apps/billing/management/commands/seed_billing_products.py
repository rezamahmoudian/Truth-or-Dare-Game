from django.core.management.base import BaseCommand
from apps.billing.models import Product, ProductKind
from apps.billing.vip import DEFAULT_BENEFITS


class Command(BaseCommand):
    help = "Create inactive product drafts without prices; preserve existing operator edits."

    def handle(self, *args, **options):
        count = 0
        for credits in (3, 10, 30):
            _, created = Product.objects.get_or_create(key=f"requests-{credits}", defaults={
                "title": f"بستهٔ {credits} درخواست", "kind": ProductKind.CREDITS, "credits": credits,
                "sort_order": credits, "is_active": False,
            })
            count += created
        _, created = Product.objects.get_or_create(key="vip-30", defaults={
            "title": "VIP سی‌روزه", "kind": ProductKind.VIP, "credits": 10, "duration_days": 30,
            "sort_order": 40, "is_active": False,
            "benefits": dict(DEFAULT_BENEFITS),
        })
        count += created
        self.stdout.write(self.style.SUCCESS(f"Created {count} inactive products. No prices or balances changed."))
