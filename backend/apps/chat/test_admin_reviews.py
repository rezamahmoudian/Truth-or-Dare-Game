from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from apps.chat.models import (
    Conversation,
    ConversationStatus,
    ConversationType,
    Message,
    MessageType,
    Participant,
)


class ChatReviewAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username="review-admin", password="test-password"
        )
        self.target = user_model.objects.create_user(
            username="target-user", display_name="کاربر هدف"
        )
        self.other = user_model.objects.create_user(
            username="other-user", display_name="کاربر دیگر"
        )
        self.room = Conversation.objects.create(
            type=ConversationType.DIRECT, status=ConversationStatus.CLOSED
        )
        Participant.objects.bulk_create([
            Participant(conversation=self.room, user=self.target),
            Participant(conversation=self.room, user=self.other),
        ])
        Message.objects.create(conversation=self.room, sender=self.target, body="پیام اول")
        Message.objects.create(conversation=self.room, sender=self.other, body="پاسخ بررسی")
        Message.objects.create(
            conversation=self.room,
            sender=None,
            type=MessageType.SYSTEM,
            body="سیستم وارد گفتگو شد",
        )
        self.room.last_message_preview = "پاسخ بررسی"
        self.room.save(update_fields=["last_message_preview"])

    def test_search_by_username_lists_all_matching_conversations(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("chat_admin_reviews"), {"q": "target-user"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پیام اول")
        self.assertContains(response, str(self.room.pk))

    def test_index_without_search_shows_latest_conversations(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("chat_admin_reviews"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پاسخ بررسی")
        self.assertContains(response, str(self.room.pk))

    def test_detail_is_read_only_transcript(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("chat_admin_review_detail", args=[self.room.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پیام اول")
        self.assertContains(response, "پاسخ بررسی")
        self.assertContains(response, "سیستم وارد گفتگو شد")
        self.assertContains(response, "فقط برای بررسی")

    def test_staff_needs_transcript_permission(self):
        self.admin.is_superuser = False
        self.admin.save(update_fields=["is_superuser"])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("chat_admin_reviews"), {"q": "target"}).status_code, 403)

        permission = Permission.objects.get(
            content_type__app_label="chat", codename="view_chat_transcript"
        )
        self.admin.user_permissions.add(permission)
        self.assertEqual(self.client.get(reverse("chat_admin_reviews"), {"q": "target"}).status_code, 200)

    def test_admin_can_send_notice_to_users_system_inbox(self):
        self.client.force_login(self.admin)
        with patch("apps.chat.broadcast.to_users"):
            response = self.client.post(
                reverse("chat_admin_send_system", args=[self.room.pk]),
                {"target_user_id": self.target.pk, "body": "لطفاً پیام‌های گزارش‌شده را بررسی کن."},
            )
        self.assertEqual(response.status_code, 302)
        inbox = Conversation.objects.get(is_system=True, owner=self.target)
        self.assertEqual(inbox.participants.count(), 1)
        notice = inbox.messages.get()
        self.assertEqual(notice.type, MessageType.SYSTEM)
        self.assertEqual(notice.body, "لطفاً پیام‌های گزارش‌شده را بررسی کن.")
        self.assertEqual(notice.meta["system_kind"], "admin_notice")

        with patch("apps.chat.broadcast.to_users"):
            self.client.post(
                reverse("chat_admin_send_system", args=[self.room.pk]),
                {"target_user_id": self.target.pk, "body": "پیام دوم"},
            )
        self.assertEqual(Conversation.objects.filter(is_system=True, owner=self.target).count(), 1)
        self.assertEqual(inbox.messages.count(), 2)
