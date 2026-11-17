from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from apps.core.errors import DomainError
from apps.users.models import User
from apps.billing.wallets import grant_credits


class Command(BaseCommand):
    help = "Audited, idempotent support grant. Requires an authorized staff actor and reason."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Recipient username")
        parser.add_argument("--actor", required=True, help="Staff username with billing.adjust_wallet permission")
        parser.add_argument("--amount", type=int, required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--key", required=True, help="Stable idempotency key; reuse on retries")
        parser.add_argument("--expires-at", help="Optional ISO-8601 timestamp with timezone")

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["user"])
            actor = User.objects.get(username=options["actor"])
        except User.DoesNotExist:
            raise CommandError("Recipient or actor not found.")
        expiry = None
        if options["expires_at"]:
            try:
                expiry = parse_datetime(options["expires_at"])
            except ValueError:
                expiry = None
            if not expiry:
                raise CommandError("Invalid expiry timestamp.")
        try:
            grant = grant_credits(user=user, actor=actor, amount=options["amount"], reason=options["reason"], idempotency_key=options["key"], expires_at=expiry)
        except DomainError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"Grant {grant.pk}: {grant.amount} credits (replays do not add credit)."))
