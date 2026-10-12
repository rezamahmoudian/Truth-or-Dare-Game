from datetime import date

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.chat.models import Conversation, Participant, Message
from apps.users.models import User, hash_device_token


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class AccountAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.password = "Raindrop!Cedar47"

    def register(self, **kwargs):
        data = {"username": "new_player", "password": self.password, "password_confirm": self.password}
        data.update(kwargs)
        return self.client.post("/api/auth/register/", data, format="json")

    def test_register_creates_one_password_account_and_returns_authenticated_identity(self):
        response = self.register(username=" New_Player ")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="new_player")
        self.assertFalse(user.is_guest)
        self.assertFalse(user.is_onboarded)
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertEqual(int(AccessToken(response.data["access"])["user_id"]), user.pk)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access"])
        self.assertEqual(self.client.get("/api/users/me/").data["id"], user.pk)
        profile = self.client.patch("/api/users/me/", {"display_name": "رضا", "gender": "M", "birth_date": "1998-01-01"}, format="json")
        self.assertTrue(profile.data["is_onboarded"])

    def test_bad_registration_never_creates_account(self):
        for patch in [{"username": "a!"}, {"password_confirm": "different"}, {"password": "12345678", "password_confirm": "12345678"}, {"password": "short", "password_confirm": "short"}]:
            response = self.register(**patch)
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.register(username="NEW_PLAYER").status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_login_returns_original_account_and_history(self):
        user = User.objects.create_user(username="ExistingPlayer", password=self.password, is_guest=False, display_name="رضا", gender="M", birth_date=date(1998, 1, 1))
        room = Conversation.objects.create(type="DIRECT")
        Participant.objects.create(conversation=room, user=user)
        message = Message.objects.create(conversation=room, sender=user, body="previous message", type="TEXT")
        response = self.client.post("/api/auth/login/", {"username": " existingplayer ", "password": self.password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], user.pk)
        self.assertTrue(response.data["user"]["is_onboarded"])
        self.assertEqual(User.objects.count(), 1)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access"])
        history = self.client.get(f"/api/conversations/{room.pk}/messages/")
        self.assertEqual(history.status_code, 200)
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())

    def test_wrong_password_missing_disabled_and_ai_fail_without_creating_users(self):
        user = User.objects.create_user(username="existing", password=self.password, is_guest=False)
        def login(username="existing", password=None):
            return self.client.post("/api/auth/login/", {"username": username, "password": password or self.password})
        wrong = login(password="bad"); missing = login(username="missing")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.data, missing.data)
        user.is_active = False; user.save()
        self.assertEqual(login().status_code, 401)
        user.is_active = True; user.is_ai = True; user.save()
        self.assertEqual(login().status_code, 401)
        self.assertEqual(User.objects.count(), 1)

    def test_upgrade_remains_login_capable_and_device_token_cannot_bypass_password(self):
        token = "guest-device-token-" * 4
        guest = self.client.post("/api/auth/guest/", {"device_token": token})
        user_id = guest.data["user"]["id"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + guest.data["access"])
        upgraded = self.client.post("/api/auth/upgrade/", {"username": "upgraded", "password": self.password})
        self.assertEqual(upgraded.status_code, 200)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/guest/", {"device_token": token}).status_code, 409)
        login = self.client.post("/api/auth/login/", {"username": "upgraded", "password": self.password})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data["user"]["id"], user_id)

    def test_password_whitespace_is_not_changed_and_invalid_auth_header_does_not_block_login(self):
        password = "  Birch47!Rain  "
        registered = self.register(password=password, password_confirm=password)
        self.assertEqual(registered.status_code, 201)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-token")
        result = self.client.post("/api/auth/login/", {"username": "new_player", "password": password})
        self.assertEqual(result.status_code, 200)

    @override_settings(REST_FRAMEWORK={"DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"], "DEFAULT_THROTTLE_RATES": {"auth": "2/min"}})
    def test_login_is_rate_limited(self):
        from unittest.mock import patch
        from rest_framework.throttling import ScopedRateThrottle
        with patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"auth": "2/min"}):
            for _ in range(2):
                self.assertEqual(self.client.post("/api/auth/login/", {"username": "noone", "password": "bad"}).status_code, 401)
            self.assertEqual(self.client.post("/api/auth/login/", {"username": "noone", "password": "bad"}).status_code, 429)
