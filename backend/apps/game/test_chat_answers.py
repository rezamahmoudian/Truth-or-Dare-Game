from unittest.mock import patch

from django.test import TestCase

from apps.chat import services as chat
from apps.chat.models import Conversation, ConversationType, Message, MessageType, Participant
from apps.game.models import GameSession, Prompt, PromptReviewStatus, PromptType, Turn, TurnStatus
from apps.users.models import User


class ChatAnswerTests(TestCase):
    def setUp(self):
        self.player = User.objects.create_user(username="player", display_name="بازیکن")
        self.other = User.objects.create_user(username="other", display_name="هم‌بازی")
        self.conversation = Conversation.objects.create(
            type=ConversationType.DIRECT,
            status="ACTIVE",
            owner=self.player,
        )
        Participant.objects.bulk_create([
            Participant(conversation=self.conversation, user=self.player),
            Participant(conversation=self.conversation, user=self.other),
        ])
        prompt = Prompt.objects.create(
            type=PromptType.TRUTH,
            text="آخرین فیلمی که دیدی چه بود؟",
            review_status=PromptReviewStatus.APPROVED,
        )
        self.session = GameSession.objects.create(
            conversation=self.conversation,
            turn_order=[self.player.pk, self.other.pk],
            started_by=self.player,
        )
        self.turn = Turn.objects.create(
            session=self.session,
            player=self.player,
            index=0,
            status=TurnStatus.ANSWERING,
            choice=PromptType.TRUTH,
            prompt=prompt,
        )

    @patch("apps.chat.broadcast.to_users")
    def test_text_from_answerer_becomes_game_answer_and_advances_turn(self, _broadcast):
        message, created = chat.post_message(
            conversation=self.conversation,
            sender=self.player,
            body="یک فیلم کمدی دیدم",
            client_id="answer-1",
        )

        self.assertTrue(created)
        self.assertEqual(message.type, MessageType.GAME_ANSWER)
        self.assertEqual(message.meta["turn_id"], self.turn.pk)
        self.turn.refresh_from_db()
        self.assertEqual(self.turn.status, TurnStatus.CONFIRMING)
        self.assertEqual(self.turn.answer_message_id, message.pk)

    @patch("apps.chat.broadcast.to_users")
    def test_other_player_message_stays_normal_chat(self, _broadcast):
        message, _ = chat.post_message(
            conversation=self.conversation,
            sender=self.other,
            body="چه جالب!",
            client_id="chat-1",
        )

        self.assertEqual(message.type, MessageType.TEXT)
        self.turn.refresh_from_db()
        self.assertEqual(self.turn.status, TurnStatus.ANSWERING)

    @patch("apps.chat.broadcast.to_users")
    def test_retry_returns_same_answer_without_creating_another_message(self, _broadcast):
        first, created = chat.post_message(
            conversation=self.conversation,
            sender=self.player,
            body="جواب اول",
            client_id="answer-retry",
        )
        second, duplicate = chat.post_message(
            conversation=self.conversation,
            sender=self.player,
            body="جواب اول",
            client_id="answer-retry",
        )

        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(
            Message.objects.filter(conversation=self.conversation).count(), 1
        )

    @patch("apps.chat.broadcast.to_users")
    def test_message_after_answer_is_normal_chat(self, _broadcast):
        chat.post_message(
            conversation=self.conversation,
            sender=self.player,
            body="جواب اول",
            client_id="answer-1",
        )
        message, _ = chat.post_message(
            conversation=self.conversation,
            sender=self.player,
            body="حالا تو جواب بده",
            client_id="chat-2",
        )

        self.assertEqual(message.type, MessageType.TEXT)
        self.assertEqual(Message.objects.filter(type=MessageType.GAME_ANSWER).count(), 1)
