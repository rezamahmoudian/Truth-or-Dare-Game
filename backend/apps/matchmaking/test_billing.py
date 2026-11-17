from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai_players.services import match_ticket
from apps.billing import wallets
from apps.billing.models import GrantSource, LedgerKind, MatchCreditReservation, ReservationStatus, WalletLedger
from apps.chat import services as chat
from apps.chat.models import Conversation
from apps.core.errors import DomainError
from apps.matchmaking import quota, services
from apps.matchmaking.models import MatchMode, MatchTicket, TicketState
from apps.users.models import User


class Fixtures:
    def setUp(self):
        for target in ("apps.chat.broadcast.to_users", "apps.ai_players.services.notify"):
            mock = patch(target)
            mock.start()
            self.addCleanup(mock.stop)
        self.user = User.objects.create_user(username="payer", display_name="اول", gender="M", birth_date=date(1995, 1, 1))
        self.other = User.objects.create_user(username="partner", display_name="دوم", gender="F", birth_date=date(1995, 1, 1))
        self.admin = User.objects.create_user(username="staff", is_staff=True, is_superuser=True)
        self.mode = MatchMode.objects.create(key="paid", title="انتخاب دختر", requires_premium=True, target_gender="F")
        self.quick = MatchMode.objects.create(key="free", title="سریع")

    def grant(self, amount=1, **kwargs):
        return wallets.grant_credits(user=self.user, actor=self.admin, amount=amount,
            reason="اعتبار تست", idempotency_key=str(uuid4()), **kwargs)

    def enter(self):
        return services.enqueue(self.user, self.mode.key, use_credit=True)

    def match(self):
        self.ticket = self.enter()
        self.partner_ticket = services.enqueue(self.other, self.quick.key)
        self.room = services._commit_group([self.ticket, self.partner_ticket])
        self.assertIsNotNone(self.room)
        self.ticket.refresh_from_db()
        self.at = self.ticket.matched_at

    def send(self, user, second, key=None):
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(seconds=second)):
            return chat.post_message(conversation=self.room, sender=user, body="سلام دوست من", client_id=key)

    def balance(self, available, reserved=0):
        snap = wallets.wallet_snapshot(self.user)
        self.assertEqual((snap["available"], snap["reserved"]), (available, reserved))
        entries = WalletLedger.objects.filter(wallet__user=self.user)
        self.assertEqual(sum(e.delta for e in entries), available + reserved)
        self.assertEqual(sum(e.reserved_delta for e in entries), reserved)


@override_settings(AI_PLAYERS_ENABLED=False)
class MatchBillingTests(Fixtures, TestCase):
    def test_free_quota_before_wallet_and_paid_usage_separate(self):
        self.grant(2)
        self.mode.requires_premium = False
        self.mode.daily_limit = 1
        self.mode.save()
        self.match()
        self.assertFalse(self.ticket.uses_credit)
        self.balance(2)
        self.send(self.user, 60)
        self.send(self.other, 61)
        self.assertEqual(services.used_today(self.user, self.mode), 1)
        self.match()
        self.assertTrue(self.ticket.uses_credit)
        self.balance(1, 1)
        self.send(self.user, 60)
        self.send(self.other, 61)
        self.balance(1)
        self.assertEqual(services.used_today(self.user, self.mode), 1)

    def test_confirmation_and_no_funds_do_not_create_ticket(self):
        with self.assertRaises(DomainError):
            self.enter()
        self.grant()
        with self.assertRaises(DomainError) as error:
            services.enqueue(self.user, self.mode.key)
        self.assertEqual(error.exception.code, "credit_confirmation_required")
        self.assertFalse(MatchTicket.objects.exists())
        self.balance(1)

    def test_reserve_replay_and_cancel_exactly_once(self):
        self.grant()
        ticket = self.enter()
        self.assertEqual(services.enqueue(self.user, self.mode.key).pk, ticket.pk)
        self.assertIsNone(ticket.ai_fallback_at)
        self.balance(0, 1)
        services.cancel(self.user)
        services.cancel(self.user)
        self.balance(1)
        self.assertEqual(WalletLedger.objects.filter(kind=LedgerKind.RESERVE).count(), 1)
        self.assertEqual(WalletLedger.objects.filter(kind=LedgerKind.RELEASE).count(), 1)

    def test_mode_switch_reuses_released_last_credit(self):
        self.grant()
        first = self.enter()
        mode = MatchMode.objects.create(key="paid-two", title="ویژه", requires_premium=True)
        second = services.enqueue(self.user, mode.key, use_credit=True)
        first.refresh_from_db()
        self.assertEqual(first.state, TicketState.CANCELLED)
        self.assertNotEqual(first.pk, second.pk)
        self.balance(0, 1)

    def test_failed_switch_keeps_original_search(self):
        self.grant()
        first = self.enter()
        mode = MatchMode.objects.create(key="paid-two", title="ویژه", requires_premium=True)
        with self.assertRaises(DomainError):
            services.enqueue(self.user, mode.key)
        first.refresh_from_db()
        self.assertEqual(first.state, TicketState.QUEUED)
        self.balance(0, 1)

    def test_bilateral_engagement_consumes_exactly_once(self):
        self.grant()
        self.match()
        self.send(self.user, 1)
        self.send(self.other, 2)
        self.send(self.user, 60, "one")
        self.balance(0, 1)
        self.send(self.other, 61, "two")
        self.send(self.other, 62, "two")
        self.send(self.user, 63)
        self.balance(0)
        chat.close_room(self.user, self.room)
        self.balance(0)
        self.assertEqual(WalletLedger.objects.filter(kind=LedgerKind.CONSUME).count(), 1)

    def test_later_mode_edit_does_not_break_existing_human_chat(self):
        self.grant()
        self.match()
        self.mode.is_ai = True
        self.mode.save(update_fields=["is_ai"])
        self.send(self.user, 60)
        self.send(self.other, 61)
        self.balance(0)

    def test_close_delete_leave_release_and_later_messages_stay_free(self):
        self.grant()
        for action in (chat.close_room, chat.delete_for_me, chat.leave):
            with self.subTest(action=action.__name__):
                self.match()
                self.send(self.user, 1)
                self.send(self.other, 2)
                action(self.user, self.room)
                self.balance(1)
                self.room = chat.get_or_create_pair(self.user, self.other)
                self.send(self.user, 60)
                self.send(self.other, 61)
                self.balance(1)

    def test_new_search_seals_old_match_and_releases_hold(self):
        self.grant()
        self.match()
        old = self.ticket
        self.match()
        old.refresh_from_db()
        self.assertIsNotNone(old.quota_closed_at)
        self.assertEqual(MatchCreditReservation.objects.get(ticket=old).status, ReservationStatus.RELEASED)
        self.balance(0, 1)

    def test_stale_search_releases_credit(self):
        self.grant()
        ticket = self.enter()
        ticket.created_at -= timedelta(hours=1)
        ticket.save(update_fields=["created_at"])
        self.assertEqual(services._expire_stale([ticket]), 1)
        self.balance(1)

    def test_paid_filter_never_widens_or_falls_back_to_ai(self):
        self.grant()
        ticket = self.enter()
        ticket.created_at -= timedelta(minutes=1)
        ticket.ai_fallback_at = timezone.now() - timedelta(minutes=1)
        ticket.save()
        self.assertEqual(services._widen_overdue([ticket]), 0)
        self.assertFalse(match_ticket(ticket))
        self.other.gender = "M"
        self.other.save(update_fields=["gender"])
        other = services.enqueue(self.other, self.quick.key)
        ticket.widened = True  # Even legacy/corrupt widening cannot relax paid filters.
        self.assertFalse(services._compatible(ticket, other))
        self.assertIsNone(services._commit_group([ticket, other]))
        self.assertFalse(Conversation.objects.exists())
        self.balance(0, 1)

    def test_expired_grant_cannot_start_match_or_create_ghost_room(self):
        self.grant(expires_at=timezone.now() + timedelta(seconds=20))
        ticket = self.enter()
        other = services.enqueue(self.other, self.quick.key)
        with patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(seconds=30)):
            self.assertIsNone(services._commit_group([ticket, other]))
            self.assertFalse(Conversation.objects.exists())
            self.assertEqual(services._expire_stale([ticket]), 1)
            self.balance(0)

    def test_expired_grant_does_not_break_chat_or_charge_another_grant(self):
        self.grant(expires_at=timezone.now() + timedelta(seconds=30))
        self.grant(2)
        self.match()
        self.send(self.user, 60)
        self.send(self.other, 61)
        self.balance(2)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.quota_consumed_at)
        self.assertIsNotNone(self.ticket.quota_closed_at)

    def test_abandoned_matched_hold_expires_without_ending_chat(self):
        self.grant()
        self.match()
        with patch("django.utils.timezone.now", return_value=self.ticket.funding_expires_at + timedelta(seconds=1)):
            quota.expire_pending()
            quota.expire_pending()
        self.balance(1)
        self.send(self.user, 1000)
        self.send(self.other, 1001)
        self.balance(1)

    @override_settings(BILLING_ORDERS_ENABLED=True)
    def test_vip_period_credit_is_reserved_before_purchase_or_support(self):
        from apps.billing import services as billing
        from apps.billing.models import Product, ProductOffer
        self.grant()
        product = Product.objects.create(key="vip-test", title="VIP", kind="VIP", credits=1, duration_days=30, is_active=True)
        offer = ProductOffer.objects.create(key="vip-test", product=product, amount=10000, is_active=True)
        order = billing.create_order(user=self.user, offer_id=offer.pk, idempotency_key="vip")
        attempt = billing.create_payment_attempt(user=self.user, order_id=order.pk, provider="test", idempotency_key="vip")
        billing.bind_provider_reference(attempt_id=attempt.pk, reference="verified-test")
        billing.record_verified_payment(attempt_id=attempt.pk, provider_reference="verified-test", transaction_id="test", amount=10000, currency="IRR")
        billing.fulfill_order(order.pk)
        ticket = self.enter()
        self.assertEqual(MatchCreditReservation.objects.get(ticket=ticket).entitlement.source, GrantSource.VIP)

    def test_http_requires_boolean_confirmation_and_reports_hold(self):
        self.grant()
        client = APIClient()
        client.force_authenticate(self.user)
        self.assertEqual(client.post("/api/match/", {"mode": self.mode.key, "use_credit": "true"}, format="json").status_code, 409)
        result = client.post("/api/match/", {"mode": self.mode.key, "use_credit": True}, format="json")
        self.assertEqual(result.status_code, 201)
        self.assertTrue(result.data["uses_credit"])
        self.assertEqual(result.data["credit_status"], ReservationStatus.HELD)
        client.force_authenticate(self.other)
        self.assertEqual(client.get(f"/api/match/?ticket_id={result.data['id']}").data["state"], "IDLE")
        client.delete("/api/match/")
        self.balance(0, 1)

    def test_accepting_invite_releases_queued_credit(self):
        from apps.users import invitations
        self.grant()
        ticket = self.enter()
        with patch("apps.chat.presence.app_online_ids", return_value=[self.user.pk, self.other.pk]):
            invite = invitations.send(self.user, self.other.pk)
        invitations.respond(self.other, invite.pk, "accept")
        ticket.refresh_from_db()
        self.assertEqual(ticket.state, TicketState.CANCELLED)
        self.balance(1)

    def test_late_cancel_recovers_matched_room_without_losing_hold(self):
        self.grant()
        self.match()
        client = APIClient()
        client.force_authenticate(self.user)
        result = client.delete(f"/api/match/?ticket_id={self.ticket.pk}")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["conversation_id"], str(self.room.pk))
        self.balance(0, 1)

    def test_cancel_old_ticket_does_not_cancel_new_search(self):
        self.grant()
        first = self.enter()
        services.cancel(self.user)
        second = self.enter()
        services.cancel(self.user, ticket_id=first.pk)
        second.refresh_from_db()
        self.assertEqual(second.state, TicketState.QUEUED)
        self.balance(0, 1)


@override_settings(AI_PLAYERS_ENABLED=False)
class MatchBillingRaces(Fixtures, TransactionTestCase):
    def race(self, *jobs):
        barrier = Barrier(len(jobs))
        def run(job):
            try:
                barrier.wait(timeout=5)
                return job()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            results = [pool.submit(run, job) for job in jobs]
            return [result.result(timeout=15) for result in results]

    def test_two_enqueues_hold_last_credit_once(self):
        self.grant()
        rows = self.race(self.enter, self.enter)
        self.assertEqual(rows[0].pk, rows[1].pk)
        self.balance(0, 1)
        self.assertEqual(MatchCreditReservation.objects.count(), 1)

    def test_cancel_racing_match_has_consistent_funding(self):
        self.grant()
        ticket = self.enter()
        partner = services.enqueue(self.other, self.quick.key)
        self.race(lambda: services.cancel(self.user), lambda: services._commit_group([ticket, partner]))
        ticket.refresh_from_db()
        reservation = MatchCreditReservation.objects.get(ticket=ticket)
        if ticket.state == TicketState.MATCHED:
            self.assertEqual(reservation.status, ReservationStatus.HELD)
            self.balance(0, 1)
        else:
            self.assertEqual(ticket.state, TicketState.CANCELLED)
            self.assertEqual(reservation.status, ReservationStatus.RELEASED)
            self.assertFalse(Conversation.objects.exists())
            self.balance(1)

    def test_close_racing_consumption_never_double_settles(self):
        self.grant()
        self.match()
        # Backdate the connection so both threads use the real clock.
        MatchTicket.objects.filter(conversation=self.room).update(matched_at=timezone.now() - timedelta(seconds=70))
        chat.post_message(conversation=self.room, sender=self.user, body="سلام")
        def reply():
            try:
                chat.post_message(conversation=self.room, sender=self.other, body="سلام")
            except DomainError:
                pass  # Closing the room may win the lock.
        self.race(reply, lambda: chat.close_room(self.user, self.room))
        result = MatchCreditReservation.objects.get(ticket=self.ticket)
        self.assertIn(result.status, [ReservationStatus.CONSUMED, ReservationStatus.RELEASED])
        self.balance(0 if result.status == ReservationStatus.CONSUMED else 1)
        self.assertEqual(WalletLedger.objects.filter(kind__in=[LedgerKind.CONSUME, LedgerKind.RELEASE]).count(), 1)

    def test_game_stat_update_under_room_lock_does_not_deadlock_new_search(self):
        from django.db import transaction
        self.grant()
        self.match()
        def game_stat():
            with transaction.atomic():
                Conversation.objects.select_for_update().get(pk=self.room.pk)
                User.objects.get(pk=self.user.pk).record_play()
        self.race(game_stat, self.enter)
        self.balance(0, 1)
