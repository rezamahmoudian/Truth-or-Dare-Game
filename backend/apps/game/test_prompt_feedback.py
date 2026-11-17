from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.chat.models import Conversation, ConversationType, Message, MessageType, Participant
from apps.chat.payloads import message_payload
from apps.game import services
from apps.game.models import Prompt, PromptFeedback, PromptFeedbackValue, PromptReviewStatus, PromptType


class PromptFeedbackTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.player = user_model.objects.create_user(username="feedback-player", display_name="بازیکن")
        self.other = user_model.objects.create_user(username="feedback-other", display_name="هم‌بازی")
        self.conversation = Conversation.objects.create(
            type=ConversationType.DIRECT, status="ACTIVE", owner=self.player
        )
        Participant.objects.bulk_create([
            Participant(conversation=self.conversation, user=self.player),
            Participant(conversation=self.conversation, user=self.other),
        ])
        self.prompt = Prompt.objects.create(
            text="چه چیزی امروز خوشحالت کرد؟",
            type=PromptType.TRUTH,
            review_status=PromptReviewStatus.APPROVED,
            is_active=True,
        )
        self.message = Message.objects.create(
            conversation=self.conversation,
            type=MessageType.GAME_PROMPT,
            body=self.prompt.text,
            meta={"prompt_id": self.prompt.pk, "choice": PromptType.TRUTH},
        )

    @patch("apps.game.services.broadcast.to_conversation")
    def test_user_can_change_one_vote_and_counts_are_broadcast(self, broadcast):
        with self.captureOnCommitCallbacks(execute=True):
            first = services.set_prompt_feedback(
                self.player, self.conversation.pk, self.message.pk, PromptFeedbackValue.POSITIVE
            )
        self.assertEqual(first["positive_count"], 1)
        self.assertEqual(PromptFeedback.objects.count(), 1)

        with self.captureOnCommitCallbacks(execute=True):
            second = services.set_prompt_feedback(
                self.player, self.conversation.pk, self.message.pk, PromptFeedbackValue.NEGATIVE
            )
        self.assertEqual(second["positive_count"], 0)
        self.assertEqual(second["negative_count"], 1)
        self.assertEqual(PromptFeedback.objects.get().value, PromptFeedbackValue.NEGATIVE)
        self.assertEqual(broadcast.call_count, 2)

    @patch("apps.game.services.broadcast.to_conversation")
    def test_history_payload_contains_counts_and_viewers_vote(self, _broadcast):
        with self.captureOnCommitCallbacks(execute=True):
            services.set_prompt_feedback(
                self.player, self.conversation.pk, self.message.pk, PromptFeedbackValue.POSITIVE
            )
        payload = message_payload(self.message, self.player)
        self.assertEqual(payload["meta"]["feedback"]["positive_count"], 1)
        self.assertEqual(payload["meta"]["feedback"]["user_value"], PromptFeedbackValue.POSITIVE)
