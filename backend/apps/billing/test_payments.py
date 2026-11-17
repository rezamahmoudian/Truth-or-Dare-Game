"""In-process bank double. Never registered or enabled by application settings."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.errors import DomainError
from . import payments, services, wallets
from .gateways import Gateway, CheckoutResult, VerificationResult, GatewayUnavailable, payments_enabled
from .models import Order, PaymentAttempt, PaymentCheckout, PaymentStatus, WalletLedger
from .tests import Fixtures


class FakeGateway(Gateway):
    is_test = True
    start_is_idempotent = True
    redirect_hosts = ("bank.example.test",)
    requests = {}
    starts = 0
    verifications = 0
    outcome = "PENDING"
    network_in_transaction = []

    def configured(self):
        return True

    def start(self, payment):
        type(self).starts += 1
        type(self).network_in_transaction.append(connection.in_atomic_block)
        type(self).requests[payment.key] = payment
        return CheckoutResult(payment.key, f"https://bank.example.test/pay/{payment.key}")

    def verify(self, *, reference, amount, currency):
        type(self).verifications += 1
        type(self).network_in_transaction.append(connection.in_atomic_block)
        original = type(self).requests[reference]
        return VerificationResult(type(self).outcome, reference, "tx-" + reference, original.amount, original.currency)


PAYMENT_SETTINGS = dict(DEBUG=True, BILLING_ORDERS_ENABLED=True, BILLING_PAYMENTS_ENABLED=True,
    BILLING_GATEWAY="test", BILLING_GATEWAY_ADAPTERS={"test": "apps.billing.test_payments.FakeGateway"},
    BILLING_PUBLIC_BASE_URL="https://game.example.test")


class PaymentFixtures(Fixtures):
    def setUp(self):
        super().setUp()
        FakeGateway.requests = {}
        FakeGateway.starts = FakeGateway.verifications = 0
        FakeGateway.outcome = "PENDING"
        FakeGateway.network_in_transaction = []
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_authenticate(self.user)
        for target in ("apps.chat.broadcast.to_users", "apps.billing.tasks.process_payment.delay"):
            mock = patch(target)
            mock.start()
            self.addCleanup(mock.stop)

    def start(self, order=None, key="first"):
        order = order or self.order()
        result = payments.begin_payment(user=self.user, order_id=order.pk, idempotency_key=key)
        self.checkout = PaymentCheckout.objects.get(pk=result["attempt_id"])
        self.current_order = order
        return result

    def verify_now(self, result="VERIFIED"):
        FakeGateway.outcome = result
        PaymentCheckout.objects.filter(pk=self.checkout.pk).update(next_check_at=timezone.now() - timedelta(seconds=1))
        payments.run_checkout(self.checkout.pk)
        self.checkout.refresh_from_db()
        self.current_order.refresh_from_db()


@override_settings(**PAYMENT_SETTINGS)
class PaymentFlowTests(PaymentFixtures, TestCase):
    def test_expired_failed_order_allows_fresh_purchase_instead_of_dead_end(self):
        self.start()
        self.verify_now("FAILED")
        with patch("django.utils.timezone.now", return_value=self.current_order.expires_at):
            result = payments.payment_payload(self.current_order)
        self.assertEqual(result["state"], "EXPIRED")
        self.assertFalse(result["can_start"])
        self.assertIsNone(result["redirect_url"])

    def test_expired_unknown_payment_stays_pending_for_recovery(self):
        self.start()
        with patch("django.utils.timezone.now", return_value=self.current_order.expires_at):
            result = payments.payment_payload(self.current_order)
        self.assertEqual(result["state"], "PENDING")
        self.assertFalse(result["can_start"])
        self.assertIsNone(result["redirect_url"])

    def test_expired_review_payment_cannot_be_treated_as_safe_to_repurchase(self):
        self.start()
        PaymentCheckout.objects.filter(pk=self.checkout.pk).update(needs_review=True)
        with patch("django.utils.timezone.now", return_value=self.current_order.expires_at):
            self.assertEqual(payments.payment_payload(self.current_order)["state"], "REVIEW")

    def test_ready_replay_uses_one_checkout_and_no_credits(self):
        first = self.start()
        second = self.start(self.current_order)
        self.assertEqual(first, second)
        self.assertEqual(FakeGateway.starts, 1)
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertFalse(WalletLedger.objects.exists())
        request = FakeGateway.requests[first["attempt_id"]]
        self.assertEqual(request.amount, self.offer.amount)
        self.assertIn(str(self.checkout.callback_key), request.callback_url)

    @override_settings(BILLING_GATEWAY="", BILLING_GATEWAY_ADAPTERS={})
    def test_no_gateway_is_disabled_even_with_feature_flags(self):
        self.assertFalse(payments_enabled())
        with self.assertRaises(DomainError):
            self.start()
        self.assertFalse(PaymentAttempt.objects.exists())
        self.assertFalse(self.client.get("/api/billing/catalog/").data["payment_enabled"])

    @override_settings(DEBUG=False)
    def test_test_gateway_can_never_be_enabled_in_production(self):
        self.assertFalse(payments_enabled())

    def test_only_trusted_verify_delivers_once(self):
        self.start()
        self.verify_now()
        self.assertEqual(self.current_order.status, "FULFILLED")
        self.verify_now()
        self.assert_balances(10)
        self.assertEqual(FakeGateway.verifications, 1)

    def test_forged_callback_cannot_mark_payment_success_or_redirect_elsewhere(self):
        self.start()
        self.client.force_authenticate(None)
        for method in (self.client.get, self.client.post):
            response = method(f"/api/billing/callback/{self.checkout.callback_key}/", {
                "status": "SUCCESS", "amount": 1, "transaction_id": "fake", "next": "https://evil.example"})
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response["Location"], f"https://game.example.test/shop/payment/{self.current_order.pk}")
            self.assertEqual(response["Cache-Control"], "no-store")
        self.verify_now("PENDING")
        self.assertEqual(self.current_order.status, "PENDING")
        self.assertFalse(WalletLedger.objects.exists())
        self.assertEqual(self.client.get(f"/api/billing/callback/{uuid4()}/").status_code, 404)

    def test_first_callback_is_immediate_and_repeats_are_coalesced(self):
        self.start()
        with patch("apps.billing.tasks.process_payment.delay") as dispatch:
            payments.schedule_check(self.current_order)
            payments.schedule_check(self.current_order)
        self.assertEqual(dispatch.call_count, 1)

    def test_wrong_amount_requires_review_and_grants_nothing(self):
        self.start()
        with patch.object(FakeGateway, "verify", return_value=VerificationResult("VERIFIED", str(self.checkout.pk), "tx", 1, "IRR")):
            self.verify_now()
        self.assertTrue(self.checkout.needs_review)
        self.assertEqual(self.checkout.last_code, "payment_mismatch")
        self.assertFalse(WalletLedger.objects.exists())

    def test_reference_mismatch_and_unsafe_redirect_are_rejected(self):
        with patch.object(FakeGateway, "start", return_value=CheckoutResult("ref", "javascript:alert(1)")):
            result = self.start()
        self.assertEqual(result["state"], "REVIEW")
        self.assertIsNone(result["redirect_url"])
        # Another independently payable order to test verified-reference binding.
        self.start(self.order())
        with patch.object(FakeGateway, "verify", return_value=VerificationResult("VERIFIED", "another-reference", "tx", self.offer.amount, "IRR")):
            self.verify_now()
        self.assertTrue(self.checkout.needs_review)
        self.assertFalse(WalletLedger.objects.exists())

    def test_timeout_is_pending_not_failed_and_cannot_create_second_attempt(self):
        self.start()
        with patch.object(FakeGateway, "verify", side_effect=GatewayUnavailable):
            self.verify_now()
        self.assertEqual(PaymentAttempt.objects.get(pk=self.checkout.pk).status, PaymentStatus.PENDING)
        with self.assertRaises(DomainError):
            self.start(self.current_order, key="second")
        self.verify_now()
        self.assert_balances(10)

    def test_lost_start_response_recovers_same_reference(self):
        original = FakeGateway.start
        def lost(adapter, request):
            original(adapter, request)
            raise GatewayUnavailable()
        with patch.object(FakeGateway, "start", lost):
            result = self.start()
        self.assertEqual(result["state"], "PENDING")
        self.verify_now("PENDING")
        self.assertEqual(len(FakeGateway.requests), 1)
        self.assertEqual(PaymentAttempt.objects.get(pk=self.checkout.pk).provider_reference, str(self.checkout.pk))
        self.verify_now()
        self.assert_balances(10)

    def test_non_idempotent_unknown_start_stops_for_review(self):
        with patch.object(FakeGateway, "start_is_idempotent", False), patch.object(FakeGateway, "start", side_effect=GatewayUnavailable) as start:
            result = self.start()
            self.verify_now()
            self.assertEqual(result["state"], "REVIEW")
            self.assertEqual(start.call_count, 1)
        self.assertFalse(WalletLedger.objects.exists())

    def test_definitive_failure_allows_explicit_retry(self):
        self.start()
        self.verify_now("FAILED")
        self.assertEqual(payments.payment_payload(self.current_order)["state"], "FAILED")
        self.start(self.current_order, key="second")
        self.verify_now()
        self.assertEqual(PaymentAttempt.objects.count(), 2)
        self.assert_balances(10)

    def test_late_success_after_order_expiry_is_delivered(self):
        self.start()
        with patch("django.utils.timezone.now", return_value=self.current_order.expires_at + timedelta(minutes=2)):
            self.verify_now()
        self.assert_balances(10)

    def test_pausing_new_payments_does_not_stop_verification(self):
        self.start()
        with override_settings(BILLING_PAYMENTS_ENABLED=False, BILLING_ORDERS_ENABLED=False):
            self.verify_now()
            self.assertEqual(self.current_order.status, "FULFILLED")
        self.assert_balances(10)

    def test_delivery_failure_keeps_paid_evidence_and_recovers(self):
        self.start()
        with patch("apps.billing.services.fulfill_order", side_effect=RuntimeError("delivery")):
            self.verify_now()
        self.assertEqual(self.current_order.status, "PAID")
        self.assertFalse(WalletLedger.objects.exists())
        payments.reconcile_payments()
        self.assert_balances(10)

    def test_broker_failure_leaves_durable_recovery_work(self):
        self.start()
        PaymentCheckout.objects.filter(pk=self.checkout.pk).update(updated_at=timezone.now() - timedelta(seconds=20))
        with patch("apps.billing.tasks.process_payment.delay", side_effect=RuntimeError("broker")):
            payments.schedule_check(self.current_order)
        FakeGateway.outcome = "VERIFIED"
        payments.reconcile_payments()
        self.assert_balances(10)

    def test_api_ownership_auth_and_client_payment_fields(self):
        order = self.order()
        url = f"/api/billing/orders/{order.pk}/payment/"
        self.assertEqual(self.client.post(url, {"idempotency_key": "api", "amount": 1}, format="json").status_code, 400)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(url, {"idempotency_key": "api"}, format="json").status_code, 404)
        self.assertEqual(self.client.post(f"/api/billing/orders/{order.pk}/check/").status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(url, {"idempotency_key": "api"}, format="json").status_code, 401)

    def test_stale_worker_result_is_discarded(self):
        original = FakeGateway.start
        def stale(adapter, request):
            result = original(adapter, request)
            PaymentCheckout.objects.filter(pk=request.key).update(lease_token=uuid4(), lease_until=timezone.now() - timedelta(seconds=1))
            return result
        with patch.object(FakeGateway, "start", stale):
            self.start()
        self.assertIsNone(PaymentAttempt.objects.get(pk=self.checkout.pk).provider_reference)
        self.verify_now("PENDING")
        self.verify_now()
        self.assert_balances(10)

    def test_crash_before_checkout_row_is_recovered(self):
        order = self.order()
        attempt = services.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="orphan")
        payments.reconcile_payments()
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.provider_reference)
        self.assertEqual(FakeGateway.starts, 1)

    def test_unresolved_checks_stop_for_review_without_reclassifying_as_failed(self):
        self.start()
        PaymentCheckout.objects.filter(pk=self.checkout.pk).update(checks=19)
        self.verify_now("PENDING")
        self.assertTrue(self.checkout.needs_review)
        self.assertIsNone(self.checkout.next_check_at)
        self.assertEqual(PaymentAttempt.objects.get(pk=self.checkout.pk).status, "PENDING")

    def test_malformed_configuration_keeps_catalog_disabled(self):
        with override_settings(BILLING_PUBLIC_BASE_URL="https://example.test:invalid"):
            self.assertFalse(payments_enabled())
        with override_settings(BILLING_GATEWAY_ADAPTERS=[]):
            self.assertFalse(payments_enabled())

    def test_duplicate_bank_transaction_is_flagged_for_review(self):
        self.start()
        self.verify_now()
        transaction_id = PaymentAttempt.objects.get(pk=self.checkout.pk).transaction_id
        self.start(self.order())
        with patch.object(FakeGateway, "verify", return_value=VerificationResult("VERIFIED", str(self.checkout.pk), transaction_id, self.offer.amount, "IRR")):
            self.verify_now()
        self.assertTrue(self.checkout.needs_review)
        self.assert_balances(10)


@override_settings(**PAYMENT_SETTINGS)
class PaymentRaces(PaymentFixtures, TransactionTestCase):
    def test_concurrent_start_and_verify_are_idempotent_without_network_db_locks(self):
        order = self.order()
        def parallel(jobs):
            barrier = Barrier(len(jobs))
            def run(job):
                try:
                    barrier.wait(timeout=5)
                    return job()
                finally:
                    connections.close_all()
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                futures = [pool.submit(run, job) for job in jobs]
                return [future.result(timeout=20) for future in futures]
        parallel([lambda: payments.begin_payment(user=self.user, order_id=order.pk, idempotency_key="race")] * 2)
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertEqual(FakeGateway.starts, 1)
        row = PaymentCheckout.objects.get()
        PaymentCheckout.objects.filter(pk=row.pk).update(next_check_at=timezone.now())
        FakeGateway.outcome = "VERIFIED"
        parallel([lambda: payments.run_checkout(row.pk)] * 2)
        self.assertEqual(FakeGateway.verifications, 1)
        self.assertFalse(any(FakeGateway.network_in_transaction))
        self.assert_balances(10)
