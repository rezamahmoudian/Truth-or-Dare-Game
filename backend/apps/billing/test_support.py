from django.contrib.auth.models import Permission
from django.test import TestCase, TransactionTestCase, override_settings
from django.db import connection, connections, IntegrityError, transaction
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from apps.core.errors import DomainError
from . import wallets
from .models import Entitlement, GrantStatus, LedgerKind, VIPSubscription, PaymentCheckout, PaymentAttempt, SupportOperation, WalletLedger
from .support import execute
from .tests import Fixtures


@override_settings(BILLING_ORDERS_ENABLED=True)
class FinancialSupportTests(Fixtures, TestCase):
    def support(self, action, target, key, reason="رسیدگی پشتیبانی", amount=None):
        return execute(actor=self.admin, action=action, target=str(target), idempotency_key=key,
                       reason=reason, amount=amount)

    def test_grant_is_audited_and_idempotent(self):
        first = self.support("grant", self.user.username, "comp-1", amount=3)
        second = self.support("grant", self.user.username, "comp-1", amount=3)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.result["credits_added"], 3)
        self.assertEqual(self.user.credit_wallet.ledger.filter(kind=LedgerKind.GRANT).count(), 1)
        with self.assertRaises(DomainError) as caught:
            self.support("grant", self.user.username, "comp-1", amount=4)
        self.assertEqual(caught.exception.code, "idempotency_conflict")

    def test_debit_only_unreserved_credit(self):
        grant = self.grant(amount=5)
        wallets.reserve_credit(user=self.user, ticket_id=self.ticket().pk)
        result = self.support("debit", grant.pk, "debit-1", amount=2)
        grant.refresh_from_db()
        self.assertEqual((grant.remaining, result.result["credits_removed"]), (3, 2))
        with self.assertRaises(DomainError):
            self.support("debit", grant.pk, "debit-2", amount=3)
        self.assert_balances(2, reserved=1)

    def test_non_superuser_needs_explicit_permission(self):
        self.admin.is_superuser = False
        self.admin.save(update_fields=["is_superuser"])
        with self.assertRaises(DomainError) as caught:
            self.support("grant", self.user.username, "no-perm", amount=1)
        self.assertEqual(caught.exception.code, "forbidden")
        self.admin.user_permissions.add(Permission.objects.get(codename="adjust_wallet", content_type__app_label="billing"))
        for cache in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            self.admin.__dict__.pop(cache, None)
        self.assertEqual(self.support("grant", self.user.username, "with-perm", amount=1).result["credits_added"], 1)

    def test_retry_delivery_requires_verified_evidence(self):
        unpaid = self.order()
        with self.assertRaises(DomainError):
            self.support("retry_delivery", unpaid.pk, "unpaid")
        order, _ = self.verified()
        self.assertEqual(order.status, "PAID")
        op = self.support("retry_delivery", order.pk, "delivery-1")
        order.refresh_from_db()
        self.assertEqual((order.status, op.result["status"]), ("FULFILLED", "FULFILLED"))
        self.support("retry_delivery", order.pk, "delivery-2")
        self.assert_balances(10)

    def vip_order(self):
        self.product.kind = "VIP"
        self.product.duration_days = 30
        self.product.save()
        return self.purchased()

    def test_revoke_active_vip_once_and_keep_history(self):
        order = self.vip_order()
        vip = VIPSubscription.objects.get(order=order)
        self.support("revoke_vip", vip.pk, "revoke-1")
        self.support("revoke_vip", vip.pk, "revoke-1")
        vip.refresh_from_db()
        self.assertIsNotNone(vip.revoked_at)
        self.assertFalse(wallets.wallet_snapshot(self.user)["vip"]["active"])
        self.assert_balances(0)
        self.assertEqual(WalletLedger.objects.filter(kind=LedgerKind.ADJUST).count(), 1)
        self.assertEqual(Entitlement.objects.get(order=order).status, GrantStatus.REVOKED)

    def test_revoke_future_vip_never_activates_credits(self):
        first = self.vip_order()
        future = self.vip_order()
        vip = VIPSubscription.objects.get(order=future)
        self.support("revoke_vip", vip.pk, "future-revoke")
        with patch("apps.billing.wallets.timezone.now", return_value=vip.starts_at + timedelta(days=1)):
            self.assert_balances(0)
        self.assertIsNone(VIPSubscription.objects.get(order=first).revoked_at)
        self.assertEqual(Entitlement.objects.get(order=future).status, GrantStatus.REVOKED)

    def test_revoke_held_vip_rejected_atomically(self):
        order = self.vip_order()
        wallets.reserve_credit(user=self.user, ticket_id=self.ticket().pk)
        vip = VIPSubscription.objects.get(order=order)
        with self.assertRaises(DomainError) as caught:
            self.support("revoke_vip", vip.pk, "held")
        self.assertEqual(caught.exception.code, "credit_reserved")
        self.assertIsNone(VIPSubscription.objects.get(pk=vip.pk).revoked_at)
        self.assertFalse(SupportOperation.objects.exists())
        self.assert_balances(9, reserved=1)

    def checkout(self, reference="ref"):
        order = self.order()
        attempt = PaymentAttempt.objects.create(order=order, provider="test", provider_reference=reference,
                                                idempotency_key="test")
        return PaymentCheckout.objects.create(attempt=attempt, needs_review=True, next_check_at=None, checks=20)

    def test_payment_review_only_schedules_verification_and_preserves_evidence(self):
        row = self.checkout()
        with patch("apps.billing.support.dispatch_check") as dispatch, self.captureOnCommitCallbacks(execute=True):
            op = self.support("review_payment", row.pk, "review-1")
            self.support("review_payment", row.pk, "review-1")
        self.assertEqual(dispatch.call_count, 1)
        row.refresh_from_db()
        self.assertFalse(row.needs_review)
        self.assertEqual(row.checks, 20)
        self.assertEqual(op.result["state"], "scheduled")
        self.assertEqual(row.attempt.status, "PENDING")
        self.assertEqual(row.attempt.order.status, "PENDING")
        self.assertFalse(WalletLedger.objects.exists())

    def test_unknown_checkout_creation_and_active_lease_cannot_be_replayed(self):
        row = self.checkout(reference=None)
        with self.assertRaises(DomainError) as caught:
            self.support("review_payment", row.pk, "unknown")
        self.assertEqual(caught.exception.code, "reference_required")
        row2 = self.checkout()
        row2.lease_until = timezone.now() + timedelta(minutes=1)
        row2.save()
        with self.assertRaises(DomainError) as caught:
            self.support("review_payment", row2.pk, "busy")
        self.assertEqual(caught.exception.code, "payment_busy")
        self.assertFalse(SupportOperation.objects.exists())

    def test_audit_is_immutable_even_with_raw_sql(self):
        op = self.support("grant", self.user.username, "audit", amount=1)
        for sql in ["UPDATE billing_supportoperation SET reason = 'tamper' WHERE id = %s",
                    "DELETE FROM billing_supportoperation WHERE id = %s"]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, [op.pk])

    def test_failed_audit_rolls_back_financial_change(self):
        with patch("apps.billing.support.SupportOperation.objects.create", side_effect=RuntimeError("db")):
            with self.assertRaises(RuntimeError):
                self.support("grant", self.user.username, "rollback", amount=3)
        self.assertFalse(WalletLedger.objects.exists())

    def test_confirmation_identity_cannot_move_to_another_user(self):
        with self.assertRaises(DomainError) as caught:
            execute(actor=self.admin, action="grant", target=self.user.username, reason="test",
                    idempotency_key="identity", amount=1, expected_user_id=self.other.pk)
        self.assertEqual(caught.exception.code, "target_changed")


class SupportConcurrencyTests(Fixtures, TransactionTestCase):
    def test_simultaneous_debits_cannot_overdraw_available_credit(self):
        grant = self.grant(amount=5)
        barrier = Barrier(2)
        def debit(key):
            try:
                barrier.wait(timeout=10)
                return execute(actor=self.admin, action="debit", target=str(grant.pk), amount=4,
                               reason="concurrent", idempotency_key=key).pk
            except DomainError as exc:
                return exc.code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(debit, ["debit-a", "debit-b"]))
        self.assertEqual(results.count("unavailable_credit"), 1)
        self.assertEqual(SupportOperation.objects.count(), 1)
        self.assert_balances(1)

    def test_double_submit_grants_once(self):
        barrier = Barrier(2)
        def grant(_):
            try:
                barrier.wait(timeout=10)
                return execute(actor=self.admin, action="grant", target=self.user.username, amount=3,
                               reason="same", idempotency_key="same").pk
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(grant, [1, 2]))
        self.assertEqual(results[0], results[1])
        self.assertEqual(SupportOperation.objects.count(), 1)
        self.assert_balances(3)
