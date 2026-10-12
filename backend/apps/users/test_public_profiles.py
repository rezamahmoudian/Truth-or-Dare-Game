from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chat.models import Conversation, Message
from apps.game.models import GameSession, Turn
from apps.users.models import User


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class PublicProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="profile-owner", display_name="آوا", birth_date=date(1998, 1, 1), gender="F")
        self.other = User.objects.create_user(username="profile-viewer", display_name="رضا")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_update_own_details_and_read_public_profile(self):
        response = self.client.patch("/api/users/me/", {"city": "شیراز", "bio": "اهل بازی و کتاب", "interests": ["موسیقی", "سفر", "موسیقی"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["interests"], ["موسیقی", "سفر"])
        self.client.force_authenticate(self.other)
        data = self.client.get(f"/api/people/{self.user.pk}/").data
        self.assertEqual(data["city"], "شیراز")
        self.assertEqual(data["bio"], "اهل بازی و کتاب")
        self.assertEqual(data["interests"], ["موسیقی", "سفر"])
        self.assertEqual(data["relation"], "NONE")
        for private in ["birth_date", "email", "password", "device_token_hash"]:
            self.assertNotIn(private, data)
        self.assertEqual(data["stats"]["games"], 0)
        self.assertFalse(any(b["earned"] for b in data["badges"]))

    def test_interests_validation_and_clear(self):
        for interests in [["x"] * 11, ["a" * 25], [" "], "music", {"music": True}]:
            response = self.client.patch("/api/users/me/", {"interests": interests}, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.patch("/api/users/me/", {"interests": [], "city": "", "bio": ""}, format="json").status_code, 200)
        self.assertEqual(self.client.patch("/api/users/me/", {"city": "a" * 65}, format="json").status_code, 400)

    def test_earned_badges_are_derived_from_real_sessions_and_completed_turns(self):
        room = Conversation.objects.create(type="DIRECT")
        session = GameSession.objects.create(conversation=room, turn_order=[self.user.pk, self.other.pk])
        answer = Message.objects.create(conversation=room, sender=self.user, body="answer", type="GAME_ANSWER")
        for i in range(10):
            Turn.objects.create(session=session, player=self.user, index=i, choice="TRUTH", status="DONE", answer_message=answer)
        Turn.objects.create(session=session, player=self.user, index=12, choice="TRUTH", status="DONE")
        Turn.objects.create(session=session, player=self.user, index=10, choice="DARE", status="SKIPPED")
        Turn.objects.create(session=session, player=self.other, index=11, choice="DARE", status="DONE")
        self.user.streak_days = 7
        self.user.last_played_on = timezone.localdate() - timedelta(days=5)
        self.user.save()
        data = self.client.get(f"/api/people/{self.user.pk}/").data
        self.assertEqual(data["stats"], {"games": 1, "truths": 10, "dares": 0, "streak_days": 0})
        earned = {b["key"] for b in data["badges"] if b["earned"]}
        self.assertEqual(earned, {"first_game", "truth"})
        self.assertEqual(data["relation"], "SELF")

    def test_no_one_can_edit_another_players_profile(self):
        response = self.client.patch(f"/api/people/{self.other.pk}/", {"city": "changed"}, format="json")
        self.assertEqual(response.status_code, 405)
        self.other.refresh_from_db(); self.assertEqual(self.other.city, "")

    def test_missing_and_inactive_users_and_authentication(self):
        self.assertEqual(self.client.get("/api/people/999999/").status_code, 404)
        self.other.is_active = False; self.other.save()
        self.assertEqual(self.client.get(f"/api/people/{self.other.pk}/").status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/people/{self.user.pk}/").status_code, 401)
