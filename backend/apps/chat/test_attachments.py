import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chat.models import Conversation, Message, Participant
from apps.chat.payloads import message_payload
from apps.users.models import Block, User


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class AttachmentTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(PRIVATE_MEDIA_ROOT=Path(self.directory.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.sender = User.objects.create_user(username="sender")
        self.recipient = User.objects.create_user(username="recipient")
        self.outsider = User.objects.create_user(username="outsider")
        self.conversation = Conversation.objects.create(type="DIRECT")
        for user in (self.sender, self.recipient):
            Participant.objects.create(conversation=self.conversation, user=user)
        self.client = APIClient()
        self.client.force_authenticate(self.sender)
        self.url = reverse("chat:attachment-upload", args=[self.conversation.pk])

    def upload(self, content=b"file contents", name="report.txt", client_id="file-1", **extra):
        return self.client.post(self.url, {
            "file": SimpleUploadedFile(name, content), "client_id": client_id, **extra,
        }, format="multipart")

    def test_upload_broadcast_history_download_and_retry(self):
        with patch("apps.chat.broadcast.to_users") as broadcast:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.upload()
            self.assertEqual(response.status_code, 201)
            self.assertEqual(broadcast.call_count, 2)
            self.assertEqual(broadcast.call_args_list[0].args[2]["attachment"]["name"], "report.txt")
            duplicate = self.upload()
            self.assertEqual(duplicate.status_code, 200)
            self.assertEqual(duplicate.data["id"], response.data["id"])
            self.assertEqual(broadcast.call_count, 2)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(len(list(Path(self.directory.name).rglob("*"))), 2)
        self.client.force_authenticate(self.recipient)
        history = self.client.get(reverse("chat:messages", args=[self.conversation.pk]))
        self.assertEqual(history.data[0]["attachment"], response.data["attachment"])
        download = self.client.get("/api" + response.data["attachment"]["url"])
        self.assertEqual(b"".join(download.streaming_content), b"file contents")
        self.assertEqual(download["Cache-Control"], "private, no-store")
        self.assertIn("attachment;", download["Content-Disposition"])

    def test_media_types_and_unsafe_files_are_downloads(self):
        cases = [
            (b"\x89PNG\r\n\x1a\n" + b"x" * 20, "image.png", "image", False),
            (b"\x00\x00\x00\x18ftypisom" + b"x" * 20, "video.mp4", "video", False),
            (b"\x1a\x45\xdf\xa3" + b"x" * 20, "voice.webm", "voice", True),
            (b"<html><script>alert(1)</script>", "image.png", "file", False),
        ]
        for index, (content, name, kind, voice) in enumerate(cases):
            response = self.upload(content, name, f"file-{index}", voice=str(voice).lower())
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data["attachment"]["kind"], kind)
        self.assertEqual(self.upload(b"not audio", "voice.webm", "bad-voice", voice="true").status_code, 400)

    def test_private_deleted_and_cleared_attachments(self):
        response = self.upload()
        path = "/api" + response.data["attachment"]["url"]
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.upload(client_id="outsider").status_code, 403)
        self.client.force_authenticate(self.recipient)
        Participant.objects.filter(user=self.recipient).update(cleared_before_id=response.data["id"])
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_authenticate(self.sender)
        Message.objects.filter(pk=response.data["id"]).update(is_deleted=True)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertIsNone(message_payload(Message.objects.get(pk=response.data["id"]))["attachment"])

    def test_rejections_do_not_leave_files(self):
        with override_settings(CHAT_UPLOAD_MAX_BYTES=3):
            self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(self.upload(b"").status_code, 400)
        self.conversation.status = "CLOSED"
        self.conversation.save()
        self.assertEqual(self.upload().status_code, 410)
        self.assertEqual(Message.objects.count(), 0)
        self.assertFalse(any(p.is_file() for p in Path(self.directory.name).rglob("*")))

    def test_blocked_and_former_members_cannot_upload(self):
        Block.objects.create(blocker=self.recipient, blocked=self.sender)
        self.assertEqual(self.upload().status_code, 403)
        Participant.objects.filter(user=self.sender).update(left_at=timezone.now())
        self.assertEqual(self.upload().status_code, 403)
        self.assertFalse(any(p.is_file() for p in Path(self.directory.name).rglob("*")))
