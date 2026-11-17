from django.test import TestCase
from rest_framework.test import APIClient

from apps.chat.models import Conversation, Participant
from apps.users.models import User


class ChatInputTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="chat-input", display_name="بازیکن")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_malformed_integer_body_fields_return_bad_request(self):
        response = self.client.post(
            "/api/conversations/rooms/", {"max_players": "bad"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "bad_number")

        conversation = Conversation.objects.create(type="DIRECT")
        Participant.objects.create(conversation=conversation, user=self.user)
        response = self.client.post(
            f"/api/conversations/{conversation.pk}/messages/",
            {"body": "سلام", "reply_to_id": "bad"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "bad_number")

        response = self.client.post(
            f"/api/conversations/{conversation.pk}/read/",
            {"up_to_message_id": "bad"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "bad_number")
