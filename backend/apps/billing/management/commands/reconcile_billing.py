from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from apps.billing.models import Order, OrderStatus, Wallet
from apps.billing.services import fulfill_order
from apps.billing.wallets import wallet_snapshot


class Command(BaseCommand):
    help = "Retry verified, undelivered orders and reconcile due credit lifecycles."

    def handle(self, *args, **options):
        delivered = synced = 0
        failures = []
        for order_id in Order.objects.filter(status=OrderStatus.PAID).values_list("id", flat=True).iterator():
            try:
                fulfill_order(order_id)
                delivered += 1
            except Exception as exc:
                failures.append(f"{order_id}: {type(exc).__name__}")
        now = timezone.now()
        wallets = Wallet.objects.filter(
            Q(entitlements__status="SCHEDULED", entitlements__starts_at__lte=now) |
            Q(entitlements__status="ACTIVE", entitlements__expires_at__lte=now),
        ).select_related("user").distinct()
        for wallet in wallets.iterator():
            wallet_snapshot(wallet.user)
            synced += 1
        self.stdout.write(f"Delivered: {delivered}; reconciled wallets: {synced}.")
        if failures:
            raise CommandError("Delivery failures requiring review: " + "; ".join(failures))
