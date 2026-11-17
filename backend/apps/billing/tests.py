from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.admin.sites import site
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.errors import DomainError
from apps.matchmaking.models import MatchMode, MatchTicket, TicketState
from apps.users.models import User
from . import services, wallets
from .models import (
    Entitlement, GrantSource, GrantStatus, LedgerKind, MatchCreditReservation,
    Order, OrderStatus, PaymentAttempt, PaymentStatus, Product, ProductKind,
    ProductOffer, ReservationStatus, VIPSubscription, Wallet, WalletLedger,
)


class Fixtures:
    def setUp(self):
        self.user = User.objects.create_user(username="billing-player", is_guest=False, gender="M", birth_date=date(1995, 1, 1))
        self.other = User.objects.create_user(username="billing-other", is_guest=False)
        self.admin = User.objects.create_user(username="billing-admin", is_staff=True, is_superuser=True)
        self.product = Product.objects.create(key="requests-test", title="ده درخواست", kind=ProductKind.CREDITS, credits=10, is_active=True)
        self.offer = ProductOffer.objects.create(key="web-test", product=self.product, amount=790000, is_active=True)
        self.mode = MatchMode.objects.create(key="billing-test", title="بازی ویژه", daily_limit=3)

    def order(self, user=None, offer=None, key=None):
        return services.create_order(user=user or self.user, offer_id=(offer or self.offer).pk, idempotency_key=key or str(uuid4()))

    def verified(self, order=None, transaction_id=None):
        order = order or self.order()
        attempt = services.create_payment_attempt(user=order.user, order_id=order.pk, provider="test-provider", idempotency_key=str(uuid4()))
        reference = str(uuid4())
        services.bind_provider_reference(attempt_id=attempt.pk, reference=reference)
        services.record_verified_payment(attempt_id=attempt.pk, provider_reference=reference, transaction_id=transaction_id or str(uuid4()), amount=order.amount, currency=order.currency)
        return Order.objects.get(pk=order.pk), PaymentAttempt.objects.get(pk=attempt.pk)

    def purchased(self, **kwargs):
        order, _ = self.verified(self.order(**kwargs))
        services.fulfill_order(order.pk)
        return Order.objects.get(pk=order.pk)

    def grant(self, amount=1, **kwargs):
        return wallets.grant_credits(user=self.user, amount=amount, actor=self.admin, reason="هدیه پشتیبانی", idempotency_key=str(uuid4()), **kwargs)

    def ticket(self, **kwargs):
        return MatchTicket.objects.create(user=self.user, mode=self.mode, state=TicketState.MATCHED, **kwargs)

    def assert_balances(self, available, reserved=0):
        snap = wallets.wallet_snapshot(self.user)
        self.assertEqual((snap["available"], snap["reserved"], snap["total"]), (available, reserved, available + reserved))
        wallet = Wallet.objects.get(user=self.user)
        rows = list(wallet.ledger.order_by("id"))
        balance = held = 0
        for row in rows:
            self.assertEqual((row.balance_before, row.reserved_before), (balance, held))
            balance += row.delta
            held += row.reserved_delta
            self.assertEqual((row.balance_after, row.reserved_after), (balance, held))
        self.assertEqual((balance, held), (wallet.balance, wallet.reserved))
        grants = list(wallet.entitlements.filter(status=GrantStatus.ACTIVE))
        self.assertEqual(sum(g.remaining for g in grants), balance)
        self.assertEqual(sum(g.reserved for g in grants), held)


@override_settings(BILLING_ORDERS_ENABLED=True)
class BillingTests(Fixtures, TestCase):
    def test_order_replay_snapshot_survives_price_and_product_edits(self):
        order = self.order(key="same")
        self.offer.amount = 999000
        self.offer.is_active = False
        self.offer.save()
        self.product.credits = 30
        self.product.title = "تغییر نام"
        self.product.save()
        replay = self.order(key="same")
        self.assertEqual(replay.pk, order.pk)
        self.assertEqual(replay.amount, 790000)
        self.assertEqual(replay.product_snapshot["credits"], 10)
        verified, _ = self.verified(order)
        services.fulfill_order(verified.pk)
        self.assert_balances(10)

    def test_order_idempotency_cannot_change_offer(self):
        self.order(key="same")
        offer = ProductOffer.objects.create(key="another", product=self.product, amount=1, is_active=True)
        with self.assertRaisesMessage(DomainError, "سفارش دیگری"):
            self.order(offer=offer, key="same")
        self.assertEqual(Order.objects.count(), 1)

    @override_settings(BILLING_ORDERS_ENABLED=False)
    def test_ordering_off_by_default_behavior(self):
        with self.assertRaises(DomainError) as caught:
            self.order()
        self.assertEqual(caught.exception.code, "billing_unavailable")
        self.assertFalse(Order.objects.exists())

    def test_unavailable_offer_windows_and_product(self):
        for changes in ({"is_active": False}, {"starts_at": timezone.now() + timedelta(days=1)}, {"starts_at": timezone.now() - timedelta(days=2), "ends_at": timezone.now() - timedelta(days=1)}):
            with self.subTest(changes=changes):
                ProductOffer.objects.filter(pk=self.offer.pk).update(**{"is_active": True, "ends_at": None, "starts_at": timezone.now() - timedelta(minutes=1), **changes})
                with self.assertRaises(DomainError):
                    self.order()
        ProductOffer.objects.filter(pk=self.offer.pk).update(is_active=True, starts_at=timezone.now(), ends_at=None)
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        with self.assertRaises(DomainError):
            self.order()

    def test_unpaid_order_cannot_deliver(self):
        order = self.order()
        with self.assertRaises(DomainError):
            services.fulfill_order(order.pk)
        self.assertFalse(Entitlement.objects.exists())

    def test_verify_and_deliver_replays_are_idempotent(self):
        order, attempt = self.verified()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertFalse(Entitlement.objects.exists())
        for _ in range(3):
            services.record_verified_payment(attempt_id=attempt.pk, provider_reference=attempt.provider_reference, transaction_id=attempt.transaction_id, amount=order.amount, currency="IRR")
            services.fulfill_order(order.pk)
        self.assertEqual(Entitlement.objects.count(), 1)
        self.assertEqual(WalletLedger.objects.count(), 1)
        self.assert_balances(10)

    def test_payment_amount_currency_and_reference_must_match(self):
        order = self.order()
        attempt = services.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="try-1")
        services.bind_provider_reference(attempt_id=attempt.pk, reference="ref")
        for changes in ({"amount": 79000}, {"amount": float(order.amount)}, {"currency": "IRT"}, {"provider_reference": "other"}):
            with self.subTest(changes=changes), self.assertRaises(DomainError):
                services.record_verified_payment(**{"attempt_id": attempt.pk, "provider_reference": "ref", "transaction_id": "tx", "amount": order.amount, "currency": "IRR", **changes})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertFalse(Entitlement.objects.exists())

    def test_transaction_reuse_across_accounts_rejected(self):
        self.verified(transaction_id="bank-tx")
        with self.assertRaises(DomainError) as caught:
            self.verified(self.order(user=self.other), transaction_id="bank-tx")
        self.assertEqual(caught.exception.code, "transaction_conflict")
        self.assertEqual(PaymentAttempt.objects.filter(status=PaymentStatus.VERIFIED).count(), 1)

    def test_provider_reference_is_unique_and_cannot_change(self):
        order, attempt = self.verified()
        with self.assertRaises(DomainError):
            services.bind_provider_reference(attempt_id=attempt.pk, reference="replacement")
        second = self.order(user=self.other)
        second_attempt = services.create_payment_attempt(user=self.other, order_id=second.pk, provider=attempt.provider, idempotency_key="second")
        with self.assertRaises(DomainError):
            services.bind_provider_reference(attempt_id=second_attempt.pk, reference=attempt.provider_reference)

    def test_pending_attempt_blocks_a_new_checkout(self):
        order = self.order()
        first = services.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="same")
        self.assertEqual(services.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="same").pk, first.pk)
        with self.assertRaises(DomainError):
            services.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="next")
        services.record_failed_payment(attempt_id=first.pk, result_code="declined")
        second = services.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="next")
        self.assertNotEqual(first.pk, second.pk)

    def test_payment_failure_cannot_downgrade_verified_evidence(self):
        order, attempt = self.verified()
        services.record_failed_payment(attempt_id=attempt.pk, result_code="late-decline")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentStatus.VERIFIED)
        services.fulfill_order(order.pk)
        self.assert_balances(10)

    def test_db_verification_cannot_have_null_amount(self):
        attempt = services.create_payment_attempt(user=self.user, order_id=self.order().pk, provider="test", idempotency_key="null-test")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAttempt.objects.filter(pk=attempt.pk).update(status=PaymentStatus.VERIFIED, verified_at=timezone.now(), verified_currency="IRR", transaction_id="tx-null", verified_amount=None)

    def test_late_verified_payment_is_recoverable_after_quote_expiry(self):
        order = self.order()
        attempt = services.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="late")
        services.bind_provider_reference(attempt_id=attempt.pk, reference="late")
        with patch("django.utils.timezone.now", return_value=order.expires_at + timedelta(minutes=2)):
            services.record_verified_payment(attempt_id=attempt.pk, provider_reference="late", transaction_id="late-tx", amount=order.amount, currency=order.currency)
            services.fulfill_order(order.pk)
        self.assert_balances(10)

    def test_delivery_failure_rolls_back_and_recovery_retries_once(self):
        order, _ = self.verified()
        with patch("apps.billing.wallets.WalletLedger.objects.create", side_effect=RuntimeError("storage failure")):
            with self.assertRaises(RuntimeError):
                services.fulfill_order(order.pk)
        self.assertFalse(Entitlement.objects.exists())
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        call_command("reconcile_billing", stdout=StringIO())
        call_command("reconcile_billing", stdout=StringIO())
        self.assert_balances(10)

    def test_support_grant_requires_permission_reason_and_idempotency(self):
        for actor, reason in [(self.user, "gift"), (self.admin, "")]:
            with self.assertRaises(DomainError):
                wallets.grant_credits(user=self.user, amount=3, actor=actor, reason=reason, idempotency_key="x")
        first = wallets.grant_credits(user=self.user, amount=3, actor=self.admin, reason="gift", idempotency_key="x")
        replay = wallets.grant_credits(user=self.user, amount=3, actor=self.admin, reason="gift", idempotency_key="x")
        self.assertEqual(first.pk, replay.pk)
        with self.assertRaises(DomainError):
            wallets.grant_credits(user=self.user, amount=30, actor=self.admin, reason="gift", idempotency_key="x")
        self.assert_balances(3)
        self.assertEqual(WalletLedger.objects.get().actor_id, self.admin.pk)

    def test_invalid_grant_amounts_and_expiry(self):
        for amount in [0, -1, True, 1.5, 1000001]:
            with self.subTest(amount=amount), self.assertRaises(DomainError):
                self.grant(amount)
        with self.assertRaises(DomainError):
            self.grant(expires_at=timezone.now() - timedelta(seconds=1))

    def test_reserve_and_release_never_consume_credit(self):
        self.grant(1)
        ticket = self.ticket()
        first = wallets.reserve_credit(user=self.user, ticket_id=ticket.pk)
        self.assertEqual(wallets.reserve_credit(user=self.user, ticket_id=ticket.pk).pk, first.pk)
        self.assert_balances(0, 1)
        for _ in range(2):
            wallets.release_credit(user=self.user, ticket_id=ticket.pk)
        self.assert_balances(1)
        self.assertEqual(wallets.reserve_credit(user=self.user, ticket_id=ticket.pk).status, ReservationStatus.RELEASED)
        self.assertEqual(wallets.consume_credit(user=self.user, ticket_id=ticket.pk).status, ReservationStatus.RELEASED)
        self.assertFalse(WalletLedger.objects.filter(kind=LedgerKind.CONSUME).exists())

    def test_consume_only_engaged_match_and_once(self):
        self.grant(2)
        ticket = self.ticket()
        wallets.reserve_credit(user=self.user, ticket_id=ticket.pk)
        with self.assertRaises(DomainError):
            wallets.consume_credit(user=self.user, ticket_id=ticket.pk)
        self.assert_balances(1, 1)
        MatchTicket.objects.filter(pk=ticket.pk).update(quota_consumed_at=timezone.now())
        for _ in range(3):
            wallets.consume_credit(user=self.user, ticket_id=ticket.pk)
        wallets.release_credit(user=self.user, ticket_id=ticket.pk)
        self.assert_balances(1)
        self.assertEqual(WalletLedger.objects.filter(kind=LedgerKind.CONSUME).count(), 1)

    def test_reservation_checks_owner_balance_state_and_ai(self):
        ticket = self.ticket()
        with self.assertRaises(DomainError):
            wallets.reserve_credit(user=self.user, ticket_id=ticket.pk)
        self.grant()
        with self.assertRaises(DomainError):
            wallets.reserve_credit(user=self.other, ticket_id=ticket.pk)
        for changes in [{"state": TicketState.CANCELLED}, {"state": TicketState.EXPIRED}, {"state": TicketState.MATCHED, "quota_closed_at": timezone.now()}]:
            MatchTicket.objects.filter(pk=ticket.pk).update(**changes)
            with self.assertRaises(DomainError):
                wallets.reserve_credit(user=self.user, ticket_id=ticket.pk)
        self.mode.is_ai = True
        self.mode.save()
        with self.assertRaises(DomainError):
            wallets.reserve_credit(user=self.user, ticket_id=self.ticket().pk)

    def test_expiry_releases_held_credit_and_is_idempotent(self):
        expiry = timezone.now() + timedelta(hours=1)
        self.grant(3, expires_at=expiry)
        ticket = self.ticket()
        wallets.reserve_credit(user=self.user, ticket_id=ticket.pk)
        with patch("django.utils.timezone.now", return_value=expiry):
            self.assert_balances(0)
            self.assert_balances(0)
            self.assertEqual(wallets.consume_credit(user=self.user, ticket_id=ticket.pk).status, ReservationStatus.EXPIRED)
        self.assertEqual(WalletLedger.objects.filter(kind=LedgerKind.EXPIRE).count(), 1)

    def vip_offer(self):
        product = Product.objects.create(key="vip-test", title="VIP", kind=ProductKind.VIP, credits=10, duration_days=30, is_active=True, benefits={"gold": True})
        return ProductOffer.objects.create(key="vip-web", product=product, amount=1490000, is_active=True)

    def test_vip_renewal_stacks_and_future_credits_wait_for_period(self):
        offer = self.vip_offer()
        self.purchased(offer=offer)
        self.purchased(offer=offer)
        periods = list(VIPSubscription.objects.order_by("starts_at"))
        self.assertEqual(periods[0].ends_at, periods[1].starts_at)
        self.assertEqual(periods[1].ends_at - periods[0].starts_at, timedelta(days=60))
        self.assertEqual(Entitlement.objects.filter(status=GrantStatus.SCHEDULED).count(), 1)
        self.assert_balances(10)
        with patch("django.utils.timezone.now", return_value=periods[1].starts_at):
            self.assert_balances(10)
            self.assertTrue(wallets.wallet_snapshot(self.user)["vip"]["active"])

    def test_vip_expiry_keeps_purchased_credits_and_uses_vip_first(self):
        self.purchased()
        self.purchased(offer=self.vip_offer())
        ticket = self.ticket()
        reservation = wallets.reserve_credit(user=self.user, ticket_id=ticket.pk)
        self.assertEqual(reservation.entitlement.source, GrantSource.VIP)
        with patch("django.utils.timezone.now", return_value=VIPSubscription.objects.get().ends_at):
            self.assert_balances(10)
            self.assertFalse(wallets.wallet_snapshot(self.user)["vip"]["active"])

    def test_skipped_future_periods_never_activate_expired_credits(self):
        offer = self.vip_offer()
        self.purchased(offer=offer)
        self.purchased(offer=offer)
        end = VIPSubscription.objects.order_by("-ends_at").first().ends_at
        with patch("django.utils.timezone.now", return_value=end + timedelta(days=1)):
            self.assert_balances(0)
            self.assertEqual(Entitlement.objects.filter(status=GrantStatus.EXPIRED).count(), 2)

    def test_ledger_and_quote_are_immutable_even_via_sql(self):
        order = self.purchased()
        entry = WalletLedger.objects.get()
        with self.assertRaises(ValidationError):
            entry.save()
        with self.assertRaises(ValidationError):
            WalletLedger.objects.filter(pk=entry.pk).update(reason="tamper")
        for sql, params in [
            ("DELETE FROM billing_walletledger WHERE id = %s", [entry.pk]),
            ("UPDATE billing_walletledger SET reason = 'tamper' WHERE id = %s", [entry.pk]),
            ("UPDATE billing_order SET amount = amount + 1 WHERE id = %s", [order.pk]),
            ("UPDATE billing_paymentattempt SET result_code = 'tamper' WHERE order_id = %s", [order.pk]),
        ]:
            with self.subTest(sql=sql), self.assertRaises(IntegrityError):
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, params)
        self.assert_balances(10)

    def test_database_rejects_negative_and_uncovered_balances(self):
        self.grant()
        for changes in [{"balance": -1}, {"reserved": 2}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Wallet.objects.filter(user=self.user).update(**changes)

    def test_seed_preserves_operator_edits_and_creates_no_prices(self):
        call_command("seed_billing_products", stdout=StringIO())
        Product.objects.filter(key="requests-10").update(title="عنوان مدیر", is_active=True)
        call_command("seed_billing_products", stdout=StringIO())
        self.assertEqual(Product.objects.get(key="requests-10").title, "عنوان مدیر")
        self.assertEqual(Product.objects.count(), 5)
        self.assertEqual(ProductOffer.objects.count(), 1)

    def test_financial_admin_cannot_change_or_forge_transactions(self):
        request = RequestFactory().get("/admin/")
        request.user = self.admin
        for model in (Wallet, WalletLedger, Order, PaymentAttempt, Entitlement, VIPSubscription, MatchCreditReservation):
            admin = site._registry[model]
            self.assertFalse(admin.has_add_permission(request))
            self.assertFalse(admin.has_change_permission(request))
            self.assertFalse(admin.has_delete_permission(request))


@override_settings(BILLING_ORDERS_ENABLED=True)
@override_settings(MONETIZATION_ENABLED=True)
class BillingAPITests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_endpoints_require_auth(self):
        for endpoint in ["catalog/", "wallet/", "orders/", "ledger/", "entitlements/"]:
            self.assertEqual(self.client.get("/api/billing/" + endpoint).status_code, 401)

    def test_orders_cannot_spoof_price_owner_or_grant_success(self):
        self.client.force_authenticate(self.user)
        base = {"offer_id": self.offer.pk, "idempotency_key": "api-create"}
        for extra in [{"amount": 1}, {"user_id": self.other.pk}, {"status": "FULFILLED"}]:
            self.assertEqual(self.client.post("/api/billing/orders/", {**base, **extra}, format="json").status_code, 400)
        result = self.client.post("/api/billing/orders/", base, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["amount"], self.offer.amount)
        self.assertEqual(self.client.post("/api/billing/orders/", base, format="json").data["id"], result.data["id"])
        self.assertEqual(self.client.post(f"/api/billing/orders/{result.data['id']}/verify/", {"success": True}, format="json").status_code, 404)

    def test_account_isolation_and_pagination(self):
        order = self.purchased()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"/api/billing/orders/{order.pk}/").status_code, 404)
        for endpoint in ["orders/", "ledger/", "entitlements/"]:
            response = self.client.get("/api/billing/" + endpoint)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["results"], [])
        self.client.force_authenticate(self.user)
        self.assertEqual(len(self.client.get("/api/billing/ledger/").data["results"]), 1)
        self.assertEqual(self.client.get("/api/billing/wallet/").data["available"], 10)

    @override_settings(BILLING_ORDERS_ENABLED=False)
    def test_catalog_and_order_flag_do_not_enable_payment(self):
        self.client.force_authenticate(self.user)
        result = self.client.get("/api/billing/catalog/")
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.data["payment_enabled"])
        self.assertFalse(result.data["orders_enabled"])
        self.assertEqual(result.data["offers"][0]["currency"], "IRR")
        result = self.client.post("/api/billing/orders/", {"offer_id": self.offer.pk, "idempotency_key": "blocked"}, format="json")
        self.assertEqual(result.status_code, 503)


@override_settings(BILLING_ORDERS_ENABLED=True)
class BillingConcurrencyTests(Fixtures, TransactionTestCase):
    def run_parallel(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            except DomainError as exc:
                return exc.code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, op) for op in operations]
            return [future.result(timeout=20) for future in futures]

    def test_concurrent_first_order_creation_is_deduplicated(self):
        result = self.run_parallel([lambda: self.order(key="parallel").pk] * 2)
        self.assertEqual(result[0], result[1])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Wallet.objects.count(), 1)

    def test_only_one_ticket_can_reserve_last_credit(self):
        self.grant(1)
        first, second = self.ticket(), self.ticket()
        result = self.run_parallel([
            lambda: wallets.reserve_credit(user=self.user, ticket_id=first.pk).status,
            lambda: wallets.reserve_credit(user=self.user, ticket_id=second.pk).status,
        ])
        self.assertCountEqual(result, [ReservationStatus.HELD, "insufficient_credit"])
        self.assert_balances(0, 1)

    def test_concurrent_fulfillment_grants_once(self):
        order, _ = self.verified()
        self.run_parallel([lambda: services.fulfill_order(order.pk)] * 2)
        self.assertEqual(Entitlement.objects.count(), 1)
        self.assert_balances(10)

    def test_concurrent_verification_and_delivery_are_idempotent(self):
        order = self.order()
        attempt = services.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="double-callback")
        services.bind_provider_reference(attempt_id=attempt.pk, reference="double-ref")
        def complete():
            services.record_verified_payment(attempt_id=attempt.pk, provider_reference="double-ref", transaction_id="double-tx", amount=order.amount, currency="IRR")
            return services.fulfill_order(order.pk).status
        self.assertEqual(self.run_parallel([complete] * 2), [OrderStatus.FULFILLED] * 2)
        self.assert_balances(10)

    def test_concurrent_vip_fulfillment_does_not_overlap_periods(self):
        product = Product.objects.create(key="vip-concurrent", title="VIP", kind=ProductKind.VIP, credits=10, duration_days=30, is_active=True)
        offer = ProductOffer.objects.create(key="vip-concurrent-web", product=product, amount=1490000, is_active=True)
        first, _ = self.verified(self.order(offer=offer))
        second, _ = self.verified(self.order(offer=offer))
        self.run_parallel([lambda: services.fulfill_order(first.pk), lambda: services.fulfill_order(second.pk)])
        periods = list(VIPSubscription.objects.order_by("starts_at"))
        self.assertEqual(periods[0].ends_at, periods[1].starts_at)
        self.assert_balances(10)

    def test_consume_and_release_race_cannot_both_win(self):
        self.grant(1)
        ticket = self.ticket()
        wallets.reserve_credit(user=self.user, ticket_id=ticket.pk)
        MatchTicket.objects.filter(pk=ticket.pk).update(quota_consumed_at=timezone.now())
        result = self.run_parallel([
            lambda: wallets.consume_credit(user=self.user, ticket_id=ticket.pk).status,
            lambda: wallets.release_credit(user=self.user, ticket_id=ticket.pk).status,
        ])
        self.assertEqual(result[0], result[1])
        self.assert_balances(0 if result[0] == ReservationStatus.CONSUMED else 1)
