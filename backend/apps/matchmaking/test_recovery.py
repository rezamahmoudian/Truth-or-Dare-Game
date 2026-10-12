from datetime import date
import uuid
from unittest.mock import patch

from django.test import override_settings
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.test import APITestCase

from apps.chat.models import Conversation
from apps.matchmaking import services
from apps.matchmaking.models import MatchMode, MatchTicket
from apps.users.models import User


@override_settings(AI_PLAYERS_ENABLED=False)
class MatchRecoveryTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="recovery-one", display_name="اول", gender="M", birth_date=date(1995, 1, 1))
        self.other = User.objects.create_user(username="recovery-two", display_name="دوم", gender="F", birth_date=date(1995, 1, 1))
        self.mode = MatchMode.objects.create(key="recovery-quick", title="شروع سریع")
        self.client.force_authenticate(self.user)

    def ticket(self, user, **kwargs):
        return MatchTicket.objects.create(user=user, mode=self.mode, my_gender=user.gender, **kwargs)

    @patch("apps.chat.broadcast.to_users")
    def test_missed_match_can_be_recovered_by_own_ticket(self, broadcast):
        first = self.ticket(self.user)
        second = self.ticket(self.other)
        services._match_once()
        first.refresh_from_db()
        second.refresh_from_db()
        response = self.client.get("/api/match/", {"ticket_id": first.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "MATCHED")
        self.assertEqual(response.data["conversation_id"], str(second.conversation_id))
        self.assertEqual(response.data["queue_size"], 0)
        # Normal home visits must not reopen an old conversation.
        self.assertEqual(self.client.get("/api/match/").data, {"state": "IDLE"})

    def test_ticket_lookup_is_owned_and_validated(self):
        theirs = self.ticket(self.other)
        self.assertEqual(self.client.get("/api/match/", {"ticket_id": theirs.pk}).data, {"state": "IDLE"})
        for raw_id in ("invalid", "0", "-1"):
            self.assertEqual(self.client.get("/api/match/", {"ticket_id": raw_id}).status_code, 400)

    def test_cancelled_ticket_does_not_return_an_older_match(self):
        old = self.ticket(self.user, state="MATCHED", conversation=Conversation.objects.create(type="ROOM"))
        pending = self.ticket(self.user, state="CANCELLED")
        response = self.client.get("/api/match/", {"ticket_id": pending.pk})
        self.assertEqual(response.data["state"], "CANCELLED")
        self.assertIsNone(response.data["conversation_id"])
        self.assertNotEqual(response.data["id"], old.pk)

    def test_queued_status_survives_refresh(self):
        pending = self.ticket(self.user)
        self.assertEqual(self.client.get("/api/match/").data["id"], pending.pk)
        self.assertEqual(self.client.get("/api/match/", {"ticket_id": pending.pk}).data["state"], "QUEUED")

    @patch("apps.chat.broadcast.to_users")
    def test_polling_does_not_use_enqueue_quota(self, broadcast):
        rates = {**ScopedRateThrottle.THROTTLE_RATES, "match": "1/hour", "match_status": "60/minute"}
        with patch.object(ScopedRateThrottle, "THROTTLE_RATES", rates), patch.object(ScopedRateThrottle, "cache", LocMemCache(uuid.uuid4().hex, {})):
            response = self.client.post("/api/match/", {"mode": self.mode.key}, format="json")
            self.assertEqual(response.status_code, 201)
            ticket_id = response.data["id"]
            self.assertEqual(self.client.post("/api/match/", {"mode": self.mode.key}, format="json").status_code, 429)
            for _ in range(3):
                self.assertEqual(self.client.get("/api/match/", {"ticket_id": ticket_id}).status_code, 200)
