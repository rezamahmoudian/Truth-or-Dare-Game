import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.chat.attachments import private_storage
from apps.chat.payloads import user_payload
from apps.users.models import User
from apps.users.payloads import person_payload
from apps.users.serializers import MeSerializer


class ProfilePhotoTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(PRIVATE_MEDIA_ROOT=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = User.objects.create_user(username="photo-user")
        self.other = User.objects.create_user(username="other-photo-user")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = "/api/users/me/photo/"

    def photo(self):
        data = BytesIO()
        Image.new("RGB", (900, 600), "blue").save(data, "JPEG", exif=b"Exif\x00\x00")
        return SimpleUploadedFile("my-photo.jpg", data.getvalue(), content_type="image/jpeg")

    def test_upload_normalizes_and_reaches_all_payloads(self):
        response = self.client.post(self.url, {"photo": self.photo()}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        url = response.data["avatar_url"]
        for payload in (MeSerializer(self.user).data, person_payload(self.user), user_payload(self.user)):
            self.assertEqual(payload["avatar_url"], url)
        public = APIClient().get(url)
        self.assertEqual(public.status_code, 200)
        with Image.open(BytesIO(b"".join(public.streaming_content))) as photo:
            self.assertEqual(photo.size, (512, 512))
            self.assertEqual(photo.format, "JPEG")
            self.assertFalse(photo.getexif())
        self.other.refresh_from_db()
        self.assertEqual(self.other.profile_photo, "")

    def test_replace_delete_and_disable_revoke_old_urls(self):
        first = self.client.post(self.url, {"photo": self.photo()}, format="multipart").data["avatar_url"]
        self.user.refresh_from_db()
        old_name = self.user.profile_photo
        with self.captureOnCommitCallbacks(execute=True):
            second = self.client.post(self.url, {"photo": self.photo()}, format="multipart").data["avatar_url"]
        self.assertNotEqual(first, second)
        self.assertFalse(private_storage().exists(f"avatars/{old_name}"))
        self.assertEqual(APIClient().get(first).status_code, 404)
        self.user.refresh_from_db()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(APIClient().get(second).status_code, 404)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(self.url)
        self.assertIsNone(response.data["avatar_url"])
        self.assertEqual(APIClient().get(second).status_code, 404)

    def test_invalid_missing_and_oversize_images_do_not_change_photo(self):
        self.client.post(self.url, {"photo": self.photo()}, format="multipart")
        self.user.refresh_from_db()
        original = self.user.profile_photo
        for data in ({}, {"photo": SimpleUploadedFile("bad.jpg", b"<svg></svg>", "image/jpeg")},
                     {"photo": SimpleUploadedFile("large.jpg", b"x" * (5 * 1024 * 1024 + 1), "image/jpeg")}):
            response = self.client.post(self.url, data, format="multipart")
            self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_photo, original)

    def test_authentication_and_readonly_path(self):
        self.assertEqual(APIClient().post(self.url, {"photo": self.photo()}, format="multipart").status_code, 401)
        self.assertEqual(APIClient().delete(self.url).status_code, 401)
        self.client.patch("/api/users/me/", {"avatar_url": "/evil", "profile_photo": "secret"}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_photo, "")
