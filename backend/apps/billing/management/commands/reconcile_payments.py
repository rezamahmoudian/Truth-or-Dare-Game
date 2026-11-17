from django.core.management.base import BaseCommand
from apps.billing.payments import reconcile_payments


class Command(BaseCommand):
    help = "Recover due gateway checks and deliver verified orders (no simulated payments)."

    def handle(self, *args, **options):
        count = reconcile_payments()
        self.stdout.write(f"Checked {count} due payment operations.")
