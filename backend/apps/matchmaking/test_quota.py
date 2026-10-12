from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.chat import services as chat
from apps.chat.models import MessageType
from apps.core.errors import DomainError
from apps.matchmaking import services
from apps.matchmaking.models import MatchMode, MatchTicket, TicketState
from apps.users.models import User


@override_settings(AI_PLAYERS_ENABLED=False)
class MatchQuotaTests(TestCase):
    def setUp(self):
        for target in ("apps.chat.broadcast.to_users", "apps.ai_players.services.notify"):
            mock = patch(target)
            mock.start()
            self.addCleanup(mock.stop)
        self.user = User.objects.create_user(
            username="quota-one", display_name="اول", gender="M", birth_date=date(1995, 1, 1),
        )
        self.other = User.objects.create_user(
            username="quota-two", display_name="دوم", gender="F", birth_date=date(1995, 1, 1),
        )
        self.mode = MatchMode.objects.create(key="quota-girls", title="دختر", target_gender="F", daily_limit=1)
        self.quick = MatchMode.objects.create(key="quota-quick", title="سریع")

    def match(self, mode=None):
        self.ticket = services.enqueue(self.user, (mode or self.mode).key)
        other_ticket = services.enqueue(self.other, self.quick.key)
        self.conversation = services._commit_group([self.ticket, other_ticket])
        self.ticket.refresh_from_db()
        self.at = self.ticket.matched_at
        return self.conversation

    def send(self, sender, second, **kwargs):
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(seconds=second)):
            return chat.post_message(conversation=self.conversation, sender=sender, body="سلام دوست من", **kwargs)

    def test_queue_cancel_expiry_and_reconnect_are_free(self):
        for _ in range(5):
            ticket = services.enqueue(self.user, self.mode.key)
            self.assertEqual(services.enqueue(self.user, self.mode.key).pk, ticket.pk)
            self.assertEqual(services.remaining_today(self.user, self.mode), 1)
            services.cancel(self.user)
        ticket = services.enqueue(self.user, self.mode.key)
        MatchTicket.objects.filter(pk=ticket.pk).update(state=TicketState.EXPIRED)
        self.assertEqual(services.remaining_today(self.user, self.mode), 1)
        self.assertNotEqual(services.enqueue(self.user, self.mode.key).pk, ticket.pk)

    def test_match_system_messages_and_one_sided_chat_are_free(self):
        self.match()
        self.assertEqual(services.remaining_today(self.user, self.mode), 1)
        self.send(self.user, 61)
        self.send(self.user, 100)
        self.send(self.other, 101, message_type=MessageType.GAME_PROMPT)
        self.assertEqual(services.remaining_today(self.user, self.mode), 1)

    def test_early_close_stays_free_after_reopening_chat(self):
        self.match()
        self.send(self.user, 1)
        self.send(self.other, 59)
        chat.close_room(self.user, self.conversation)
        self.assertEqual(services.remaining_today(self.user, self.mode), 1)
        self.conversation = chat.get_or_create_pair(self.user, self.other)
        self.send(self.user, 90)
        self.send(self.other, 91)
        self.assertEqual(services.remaining_today(self.user, self.mode), 1)

    def test_partner_leaving_or_deleting_chat_preserves_quota(self):
        self.match()
        self.send(self.user, 2)
        self.send(self.other, 3)
        chat.delete_for_me(self.other, self.conversation)
        self.conversation = chat.get_or_create_pair(self.user, self.other)
        self.send(self.user, 70)
        self.send(self.other, 71)
        self.assertEqual(services.remaining_today(self.user, self.mode), 1)

    def test_browser_exit_after_greeting_cannot_be_charged_by_other_player(self):
        self.match()
        self.send(self.user, 1)
        self.send(self.other, 2)
        # No explicit leave request when the opponent closes their browser.
        self.send(self.user, 100)
        self.assertEqual(services.remaining_today(self.user, self.mode), 1)

    def test_reciprocal_chat_after_grace_charges_once_and_enforces_cap(self):
        self.match()
        self.send(self.user, 60, client_id="first")
        self.assertEqual(services.remaining_today(self.user, self.mode), 1)
        self.send(self.other, 61, client_id="second")
        self.assertEqual(services.remaining_today(self.user, self.mode), 0)
        _, created = self.send(self.other, 62, client_id="second")
        self.assertFalse(created)
        self.send(self.user, 63)
        self.assertEqual(services.used_today(self.user, self.mode), 1)
        chat.close_room(self.user, self.conversation)
        self.assertEqual(services.used_today(self.user, self.mode), 1)
        with self.assertRaises(DomainError) as error:
            services.enqueue(self.user, self.mode.key)
        self.assertEqual(error.exception.code, "daily_limit")
        self.assertIsNone(services.remaining_today(self.other, self.quick))

    def test_answers_and_attachments_count_as_participation(self):
        self.match()
        self.send(self.user, 60, message_type=MessageType.GAME_ANSWER)
        self.send(self.other, 61, message_type=MessageType.ATTACHMENT, attachment_name="voice.webm")
        self.assertEqual(services.used_today(self.user, self.mode), 1)

    def test_reused_chat_does_not_charge_old_match_or_use_old_messages(self):
        self.match()
        original_ticket = self.ticket
        original_conversation = self.conversation
        self.send(self.user, 1)
        self.send(self.other, 2)
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(seconds=120)):
            self.match()
        self.assertEqual(self.conversation.pk, original_conversation.pk)
        self.send(self.user, 60)
        self.assertEqual(services.used_today(self.user, self.mode), 0)
        self.send(self.other, 61)
        self.assertEqual(services.used_today(self.user, self.mode), 1)
        original_ticket.refresh_from_db()
        self.assertIsNone(original_ticket.quota_consumed_at)
        self.assertIsNotNone(original_ticket.quota_closed_at)

    def test_rolling_day_starts_when_usage_is_consumed(self):
        self.match()
        self.send(self.user, 60)
        self.send(self.other, 61)
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(hours=24, seconds=60)):
            self.assertEqual(services.remaining_today(self.user, self.mode), 0)
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(hours=24, seconds=62)):
            self.assertEqual(services.remaining_today(self.user, self.mode), 1)

    def test_same_rule_applies_to_other_limited_modes(self):
        for index, gender in enumerate(("M", "")):
            with self.subTest(gender=gender):
                mode = MatchMode.objects.create(key=f"limited-{index}", title="محدود", target_gender=gender, daily_limit=2)
                self.match(mode)
                self.send(self.user, 60)
                self.send(self.other, 61)
                self.assertEqual(services.remaining_today(self.user, mode), 1)
