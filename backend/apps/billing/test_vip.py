from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.errors import DomainError
from apps.matchmaking.models import MatchTicket
from apps.matchmaking.services import _form_groups, _prioritise, recently_active
from apps.users.models import Block, User
from apps.users.payloads import person_payload
from apps.chat.payloads import user_payload
from . import services, support, vip, wallets
from .models import Product, ProductOffer, VIPSubscription, VIPSpotlight
from .tests import Fixtures


class VIPFixtures(Fixtures):
    def setUp(self):
        super().setUp()
        self.user.display_name = "بازیکن"
        self.user.save()
        self.vip_product = Product.objects.create(key="vip-test", title="VIP", kind="VIP", credits=10,
                                                  duration_days=30, is_active=True)
        self.vip_offer = ProductOffer.objects.create(key="vip-offer", product=self.vip_product, amount=1490000, is_active=True)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def buy_vip(self, user=None):
        order = self.purchased(user=user or self.user, offer=self.vip_offer)
        return VIPSubscription.objects.get(order=order)

    def queued(self, user, seconds=0, gender="M", want=""):
        ticket = MatchTicket.objects.create(user=user, mode=self.mode, my_gender=gender, want_gender=want)
        MatchTicket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(seconds=seconds))
        ticket.refresh_from_db()
        return ticket


@override_settings(BILLING_ORDERS_ENABLED=True)
@override_settings(MONETIZATION_ENABLED=True)
class VIPTests(VIPFixtures, TestCase):
    def test_status_rejects_future_expired_revoked_and_ai(self):
        first = self.buy_vip()
        second = self.buy_vip()
        self.assertTrue(self.api.get("/api/billing/vip/").data["active"])
        self.assertEqual(vip.membership(self.user)["next_period"]["starts_at"], second.starts_at)
        support.execute(actor=self.admin, action="revoke_vip", target=str(first.pk), reason="test", idempotency_key="revoke")
        self.assertFalse(vip.for_user(self.user)["active"])
        with patch("django.utils.timezone.now", return_value=second.starts_at):
            self.assertTrue(vip.for_user(self.user)["active"])
        with patch("django.utils.timezone.now", return_value=second.ends_at):
            self.assertFalse(vip.for_user(self.user)["active"])
        self.user.is_ai = True
        self.user.save()
        with patch("django.utils.timezone.now", return_value=second.starts_at):
            self.assertFalse(vip.for_user(self.user)["active"])

    def test_public_surfaces_batched_without_financial_details(self):
        self.buy_vip()
        people = [self.user, self.other, User.objects.get(pk=self.user.pk)]
        with self.assertNumQueries(2):
            vip.hydrate(people)
            payloads = [person_payload(user)["vip"] for user in people]
            self.assertTrue(user_payload(self.user)["vip"]["active"])
        self.assertEqual([p["active"] for p in payloads], [True, False, True])
        self.assertNotIn("benefits", payloads[0])
        self.assertNotIn("order_id", payloads[0])

    def test_profile_patch_cannot_grant_vip(self):
        result = self.api.patch("/api/users/me/", {"vip": {"active": True}}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.data["vip"]["active"])
        self.assertFalse(VIPSubscription.objects.exists())

    def test_discount_quote_is_server_owned_and_survives_expiry(self):
        period = self.buy_vip()
        expected = (self.offer.amount * 90 + 99) // 100
        catalog = self.api.get("/api/billing/catalog/").data
        offer = next(row for row in catalog["offers"] if row["id"] == self.offer.pk)
        self.assertEqual((offer["amount"], offer["vip_discount_percent"]), (expected, 10))
        self.assertEqual(next(row for row in catalog["offers"] if row["id"] == self.vip_offer.pk)["amount"], self.vip_offer.amount)
        order = self.order(key="discount")
        self.assertEqual(order.amount, expected)
        with patch("django.utils.timezone.now", return_value=period.ends_at):
            self.assertEqual(self.order(key="discount").amount, expected)
            self.assertEqual(self.order(key="after-expiry").amount, self.offer.amount)
        self.assertEqual(order.product_snapshot["pricing"]["vip_subscription_id"], period.pk)

    def test_benefits_snapshot_survives_product_edits(self):
        self.vip_product.benefits = {"request_discount_percent": 5, "queue_priority_seconds": 20, "gold_profile": False}
        self.vip_product.save()
        period = self.buy_vip()
        self.vip_product.benefits = {"request_discount_percent": 30}
        self.vip_product.save()
        self.assertEqual(vip.benefits(period.benefits)["request_discount_percent"], 5)
        self.assertFalse(vip.for_user(self.user)["gold_profile"])
        self.assertEqual(self.order().amount, (self.offer.amount * 95 + 99) // 100)

    def test_spotlight_idempotent_and_once_per_period(self):
        period = self.buy_vip()
        row = vip.activate_spotlight(user=self.user, idempotency_key="spot")
        self.assertEqual(vip.activate_spotlight(user=self.user, idempotency_key="spot").pk, row.pk)
        self.assertEqual(row.ends_at - row.starts_at, timedelta(minutes=15))
        self.assertEqual(vip.membership(self.user)["spotlight"]["remaining"], 0)
        with patch("django.utils.timezone.now", return_value=row.ends_at + timedelta(seconds=1)):
            with self.assertRaises(DomainError) as caught:
                vip.activate_spotlight(user=self.user, idempotency_key="again")
        self.assertEqual(caught.exception.code, "spotlight_used")
        next_period = self.buy_vip()
        with patch("django.utils.timezone.now", return_value=next_period.starts_at):
            renewed = vip.activate_spotlight(user=self.user, idempotency_key="next-period")
        self.assertNotEqual(period.pk, renewed.subscription_id)

    def test_spotlight_requires_vip_and_stops_at_period_end(self):
        with self.assertRaises(DomainError):
            vip.activate_spotlight(user=self.user, idempotency_key="no-vip")
        period = self.buy_vip()
        with patch("django.utils.timezone.now", return_value=period.ends_at - timedelta(minutes=2)):
            row = vip.activate_spotlight(user=self.user, idempotency_key="last-minutes")
            self.assertEqual(row.ends_at, period.ends_at)
        support.execute(actor=self.admin, action="revoke_vip", target=str(period.pk), reason="test", idempotency_key="revoke")
        self.assertFalse(vip.membership(self.user)["active"])

    def test_spotlight_never_bypasses_presence_block_or_profile_requirements(self):
        self.buy_vip()
        vip.activate_spotlight(user=self.user, idempotency_key="spot")
        with patch("apps.chat.presence.app_online_ids", return_value=[self.user.pk]):
            listed = recently_active(self.other)
            self.assertEqual([u.pk for u in listed], [self.user.pk])
            self.assertTrue(person_payload(listed[0])["spotlight"])
            Block.objects.create(blocker=self.user, blocked=self.other)
            self.assertEqual(recently_active(self.other), [])
        with patch("apps.chat.presence.app_online_ids", return_value=[]):
            self.assertEqual(recently_active(self.admin), [])

    def test_priority_is_bounded_and_regular_users_age_ahead(self):
        self.buy_vip()
        regular = self.queued(self.other, seconds=30)
        special = self.queued(self.user)
        self.assertEqual(_prioritise([regular, special])[0].pk, special.pk)
        regular.created_at -= timedelta(seconds=60)
        self.assertEqual(_prioritise([regular, special])[0].pk, regular.pk)

    def test_explicit_gender_queue_wins_over_quick_vip(self):
        self.buy_vip()
        vip_quick = self.queued(self.user, seconds=10)
        filtered = self.queued(self.other, want="F")
        arrival = self.queued(self.admin, gender="F")
        groups = _form_groups([vip_quick, filtered, arrival])
        self.assertEqual([{t.pk for t in group} for group in groups], [{filtered.pk, arrival.pk}])

    def test_vip_priority_applies_within_gender_queue_but_not_across_blocks(self):
        self.buy_vip()
        special = self.queued(self.user, want="F")
        regular = self.queued(self.other, seconds=20, want="F")
        arrival = self.queued(self.admin, gender="F")
        self.assertEqual({t.pk for t in _form_groups([regular, special, arrival])[0]}, {special.pk, arrival.pk})
        Block.objects.create(blocker=self.admin, blocked=self.user)
        self.assertEqual({t.pk for t in _form_groups([regular, special, arrival])[0]}, {regular.pk, arrival.pk})

    def test_revocation_removes_priority_and_discount(self):
        period = self.buy_vip()
        special = self.queued(self.user)
        regular = self.queued(self.other, seconds=10)
        support.execute(actor=self.admin, action="revoke_vip", target=str(period.pk), reason="test", idempotency_key="revoke")
        self.assertEqual(_prioritise([special, regular])[0].pk, regular.pk)
        self.assertEqual(self.order().amount, self.offer.amount)

    def test_spotlight_api_rejects_unauthenticated_and_client_state(self):
        self.assertEqual(APIClient().post("/api/billing/vip/spotlight/", {}).status_code, 401)
        result = self.api.post("/api/billing/vip/spotlight/", {"idempotency_key": "test", "remaining": 99}, format="json")
        self.assertEqual(result.status_code, 400)
        self.assertFalse(VIPSpotlight.objects.exists())


@override_settings(BILLING_ORDERS_ENABLED=True)
class VIPConcurrencyTests(VIPFixtures, TransactionTestCase):
    def test_simultaneous_spotlights_use_one_allowance(self):
        self.buy_vip()
        barrier = Barrier(2)
        def activate(_):
            try:
                barrier.wait(timeout=10)
                return vip.activate_spotlight(user=self.user, idempotency_key=str(uuid4())).pk
            except DomainError as exc:
                return exc.code
            finally:
                connections.close_all()
        with patch("apps.billing.vip.notify_change"), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(activate, [1, 2]))
        self.assertEqual(results.count("spotlight_active"), 1)
        self.assertEqual(VIPSpotlight.objects.count(), 1)
        self.assert_balances(10)
