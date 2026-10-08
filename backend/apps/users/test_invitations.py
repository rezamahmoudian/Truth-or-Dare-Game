from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.chat.models import Conversation, Participant
from apps.core.errors import DomainError
from apps.game.models import GameSession
from apps.matchmaking import services as matchmaking
from apps.matchmaking.models import MatchMode
from apps.users import invitations, social
from apps.users.models import Block, GameInvitation, User


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class InvitationTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username="alice", display_name="آوا", gender="F", birth_date=date(1998, 1, 1))
        self.b = User.objects.create_user(username="bob", display_name="رضا", gender="M", birth_date=date(1998, 1, 1))
        self.c = User.objects.create_user(username="carol", display_name="نیما", gender="M", birth_date=date(1998, 1, 1))
        self.client = APIClient()
        self.client.force_authenticate(self.a)
        for target in ["apps.chat.broadcast.to_users", "apps.chat.broadcast.to_conversation"]:
            mock = patch(target)
            mock.start()
            self.addCleanup(mock.stop)
        self.online = patch("apps.chat.presence.app_online_ids", return_value=[self.a.pk, self.b.pk, self.c.pk])
        self.online.start()
        self.addCleanup(self.online.stop)

    def test_online_list_random_query_excludes_self_bots_blocked_and_incomplete(self):
        bot = User.objects.create_user(username="ai", display_name="AI", is_ai=True, gender="F", birth_date=date(1998, 1, 1))
        empty = User.objects.create_user(username="empty")
        Block.objects.create(blocker=self.c, blocked=self.a)
        with patch("apps.chat.presence.app_online_ids", return_value=[self.a.pk, self.b.pk, self.c.pk, bot.pk, empty.pk]):
            with self.assertNumQueries(1):
                self.assertEqual([p.pk for p in matchmaking.recently_active(self.a)], [self.b.pk])
            data = self.client.get("/api/lobby/").data
            self.assertEqual([p["id"] for p in data["active_people"]], [self.b.pk])
        with patch("apps.chat.presence.app_online_ids", return_value=[]):
            self.assertEqual(matchmaking.recently_active(self.a), [])

    def test_request_accept_creates_one_playable_room_and_cancels_queues(self):
        mode = MatchMode.objects.create(key="test", title="بازی")
        tickets = [matchmaking.enqueue(user, mode.key) for user in [self.a, self.b]]
        sent = self.client.post(f"/api/people/{self.b.pk}/invite/")
        self.assertEqual(sent.status_code, 201)
        self.assertFalse(Conversation.objects.exists())
        invitation_id = sent.data["id"]
        self.client.force_authenticate(self.b)
        self.assertEqual(len(self.client.get("/api/game-invitations/").data["incoming"]), 1)
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(f"/api/game-invitations/{invitation_id}/accept/")
        self.assertEqual(result.status_code, 200)
        again = self.client.post(f"/api/game-invitations/{invitation_id}/accept/")
        self.assertEqual(again.data["conversation_id"], result.data["conversation_id"])
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(GameSession.objects.filter(status="ACTIVE").count(), 1)
        self.assertEqual(Participant.objects.count(), 2)
        for ticket in tickets:
            ticket.refresh_from_db()
            self.assertEqual(ticket.state, "CANCELLED")
        self.assertEqual(len(invitations.lists(self.a)["ready"]), 1)
        self.assertEqual(len(invitations.lists(self.b)["ready"]), 1)

    def test_duplicates_and_reverse_request_keep_one_pending_invitation(self):
        row = invitations.send(self.a, self.b.pk)
        self.assertEqual(invitations.send(self.a, self.b.pk).pk, row.pk)
        self.assertEqual(invitations.send(self.b, self.a.pk).pk, row.pk)
        self.assertEqual(GameInvitation.objects.count(), 1)
        self.assertFalse(Conversation.objects.exists())

    def test_authorization_decline_cancel_and_private_lists(self):
        row = invitations.send(self.a, self.b.pk)
        for user, action in [(self.a, "accept"), (self.a, "decline"), (self.b, "cancel"), (self.c, "accept")]:
            with self.assertRaises(DomainError):
                invitations.respond(user, row.pk, action)
        self.assertEqual(invitations.lists(self.c), {"incoming": [], "outgoing": [], "ready": []})
        invitations.respond(self.b, row.pk, "decline")
        self.assertFalse(invitations.lists(self.a)["outgoing"])
        with self.assertRaises(DomainError):
            invitations.respond(self.b, row.pk, "accept")
        row = invitations.send(self.a, self.b.pk)
        invitations.respond(self.a, row.pk, "cancel")
        self.assertFalse(invitations.lists(self.b)["incoming"])
        self.assertFalse(Conversation.objects.exists())

    def test_offline_self_block_and_ai_are_rejected(self):
        with patch("apps.chat.presence.app_online_ids", return_value=[]), self.assertRaises(DomainError):
            invitations.send(self.a, self.b.pk)
        with self.assertRaises(DomainError):
            invitations.send(self.a, self.a.pk)
        row = invitations.send(self.a, self.b.pk)
        Block.objects.create(blocker=self.b, blocked=self.a)
        with self.assertRaises(DomainError):
            invitations.respond(self.b, row.pk, "accept")
        self.assertFalse(invitations.lists(self.b)["incoming"])
        self.c.is_ai = True
        self.c.save()
        with self.assertRaises(DomainError):
            invitations.send(self.a, self.c.pk)

    def test_friend_requests_are_listed_and_accept_is_idempotent(self):
        self.assertEqual(self.client.post(f"/api/friends/{self.b.pk}/").status_code, 201)
        self.client.force_authenticate(self.b)
        self.assertEqual(len(self.client.get("/api/friends/").data["incoming"]), 1)
        first = self.client.post(f"/api/friends/{self.a.pk}/accept/")
        second = self.client.post(f"/api/friends/{self.a.pk}/accept/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["conversation_id"], second.data["conversation_id"])
        self.assertEqual(social.relation_to(self.a, self.b), "FRIENDS")
        self.assertEqual(Conversation.objects.filter(type="DIRECT").count(), 1)
