from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chat import services as chat
from apps.chat.models import Conversation, Participant, Message
from apps.game import services as game
from apps.game.models import GameSession
from apps.matchmaking import services as matchmaking
from apps.matchmaking.models import MatchMode, MatchTicket
from apps.users import invitations, social
from apps.users.models import User, Block


@override_settings(AI_PLAYERS_ENABLED=False, CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class PairConversationTests(TestCase):
    def setUp(self):
        self.a, self.b, self.c = [User.objects.create_user(username=name, display_name=name,
            gender="M", birth_date=date(1995, 1, 1)) for name in ("pair-a", "pair-b", "pair-c")]
        self.client = APIClient()
        self.client.force_authenticate(self.a)
        for target in ("apps.chat.broadcast.to_users", "apps.chat.broadcast.to_conversation"):
            mock = patch(target); mock.start(); self.addCleanup(mock.stop)
        mock = patch("apps.chat.presence.app_online_ids", return_value=[self.a.pk, self.b.pk, self.c.pk])
        mock.start(); self.addCleanup(mock.stop)
        self.mode = MatchMode.objects.create(key="pair-quick", title="pair", size_min=2, size_max=2)

    def room(self, users=None, **kwargs):
        room = Conversation.objects.create(type="ROOM", max_players=kwargs.pop("max_players", 2), owner=self.b, **kwargs)
        Participant.objects.bulk_create([Participant(conversation=room, user=u) for u in (users or [self.a, self.b])])
        return room

    def match(self):
        tickets = [MatchTicket.objects.create(user=u, mode=self.mode, my_gender=u.gender) for u in [self.a, self.b]]
        room = matchmaking._commit_group(tickets)
        for t in tickets:
            t.refresh_from_db(); self.assertEqual(t.conversation_id, room.pk)
            self.assertEqual(t.state, "MATCHED")
        return room

    def befriend(self):
        social.send_request(self.a, self.b.pk)
        return social.accept_request(self.b, self.a.pk)

    def test_accept_friend_does_not_create_chat_and_message_opens_once(self):
        self.befriend()
        self.assertFalse(Conversation.objects.exists())
        response = self.client.post(f"/api/friends/{self.b.pk}/conversation/")
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(self.b)
        again = self.client.post(f"/api/friends/{self.a.pk}/conversation/")
        self.assertEqual(response.data, again.data)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_friend_message_reuses_game_history_without_acceptance_messages(self):
        room = self.room()
        old = chat.post_system_message(room, "old history")
        self.befriend()
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(social.open_conversation(self.a, self.b.pk).pk, room.pk)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertTrue(Message.objects.filter(pk=old.pk, conversation=room).exists())

    def test_match_reuses_history_across_multiple_games(self):
        room = self.match()
        for _ in range(2):
            session = game.start_game(room.owner, room)
            game.end_game(session, "manual")
            self.assertEqual(self.match().pk, room.pk)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(GameSession.objects.filter(conversation=room).count(), 2)

    def test_match_reuses_direct_friend_chat(self):
        self.befriend()
        room = social.open_conversation(self.a, self.b.pk)
        self.assertEqual(self.match().pk, room.pk)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_invitation_reuses_room_even_when_recipient_owns_it(self):
        room = self.room()
        for _ in range(2):
            row = invitations.send(self.a, self.b.pk)
            result = invitations.respond(self.b, row.pk, "accept")
            self.assertEqual(result.conversation_id, room.pk)
            session = game.active_session(room.pk)
            self.assertIsNotNone(session)
            game.end_game(session, "manual")
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(len(invitations.lists(self.a)["ready"]), 1)

    def test_invitation_in_open_chat_uses_that_exact_chat(self):
        room = self.room()
        newer = self.room()
        chat.post_system_message(newer, "newer")
        row = invitations.send(self.a, self.b.pk)
        self.client.force_authenticate(self.b)
        result = self.client.post(f"/api/game-invitations/{row.pk}/accept/", {"conversation_id": str(room.pk)})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["conversation_id"], str(room.pk))
        self.assertEqual(Conversation.objects.count(), 2)

    def test_active_game_is_not_duplicated_by_invitation(self):
        room = self.room()
        session = game.start_game(self.b, room)
        row = invitations.send(self.a, self.b.pk)
        invitations.respond(self.b, row.pk, "accept")
        self.assertEqual(game.active_session(room.pk).pk, session.pk)
        self.assertEqual(GameSession.objects.count(), 1)

    def test_closed_and_left_room_reopens_without_resetting_clear_cursor(self):
        room = self.room(status="CLOSED")
        Participant.objects.filter(conversation=room, user=self.a).update(left_at=timezone.now(), hidden_at=timezone.now(), cleared_before_id=123)
        self.assertEqual(self.match().pk, room.pk)
        room.refresh_from_db(); self.assertEqual(room.status, "ACTIVE")
        p = Participant.objects.get(conversation=room, user=self.a)
        self.assertIsNone(p.left_at)
        self.assertEqual(p.cleared_before_id, 123)

    def test_group_histories_are_never_reused(self):
        group_ids = []
        for users, capacity in [([self.a, self.b], 5), ([self.a, self.b, self.c], 2)]:
            room = self.room(users, max_players=capacity)
            group_ids.append(room.pk)
            room.participants.filter(user=self.c).update(left_at=timezone.now())
        matched = self.match()
        self.assertNotIn(matched.pk, group_ids)
        self.assertEqual(Conversation.objects.count(), 3)
        self.assertEqual(matched.participants.count(), 2)

    def test_existing_history_wins_over_empty_duplicate(self):
        room = self.room()
        chat.post_system_message(room, "keep this history")
        self.room()
        self.assertEqual(self.match().pk, room.pk)

    def test_friend_chat_requires_friendship_and_honors_block(self):
        self.assertEqual(self.client.post(f"/api/friends/{self.b.pk}/conversation/").status_code, 403)
        self.befriend()
        Block.objects.create(blocker=self.b, blocked=self.a)
        self.assertEqual(self.client.post(f"/api/friends/{self.b.pk}/conversation/").status_code, 403)
        self.assertFalse(Conversation.objects.exists())

    def test_invite_cannot_target_someone_elses_chat_or_group(self):
        private = self.room([self.b, self.c])
        group = self.room(max_players=5)
        for target in [str(private.pk), str(group.pk), "invalid"]:
            row = invitations.send(self.a, self.b.pk)
            self.client.force_authenticate(self.b)
            response = self.client.post(f"/api/game-invitations/{row.pk}/accept/", {"conversation_id": target})
            self.assertIn(response.status_code, [400, 403])
            row.refresh_from_db(); self.assertEqual(row.status, "PENDING")
        self.assertFalse(GameSession.objects.exists())
