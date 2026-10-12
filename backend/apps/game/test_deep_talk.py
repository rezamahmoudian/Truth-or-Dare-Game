from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.chat.models import Conversation, Participant, Message
from apps.game import services as game
from apps.game.models import GameSession, Prompt
from apps.users.models import User, Friendship, Block


@override_settings(AI_PLAYERS_ENABLED=False, CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class DeepTalkTests(TestCase):
    def setUp(self):
        self.a, self.b, self.c = [User.objects.create_user(username=f"deep-{i}", display_name=f"player{i}", birth_date=date(1998, 1, 1), gender="M") for i in range(3)]
        self.room = Conversation.objects.create(type="ROOM", owner=self.a, max_players=2)
        Participant.objects.bulk_create([Participant(conversation=self.room, user=u) for u in [self.a, self.b]])
        self.friend = Friendship.objects.create(from_user=self.a, to_user=self.b, status="ACCEPTED")
        self.client = APIClient(); self.client.force_authenticate(self.b)
        self.url = f"/api/conversations/{self.room.pk}/game/"
        for target in ["apps.chat.broadcast.to_users", "apps.chat.broadcast.to_conversation"]:
            mock = patch(target); mock.start(); self.addCleanup(mock.stop)
        self.bold = self.prompt("bold", "BOLD", intensity=3)
        self.private = self.prompt("private", "FUNNY")
        self.prompt("ordinary", "FRIENDLY")
        self.prompt("deep category", "DEEP")
        self.prompt("pending bold", "BOLD", review_status="PENDING")
        self.prompt("inactive bold", "BOLD", is_active=False)
        self.prompt("group bold", "BOLD", min_players=4)
        self.prompt("dare", "BOLD", type="DARE")

    def prompt(self, text, category, **kwargs):
        return Prompt.objects.create(**{"text": text, "category": category, "type": "TRUTH", "review_status": "APPROVED", "is_active": True, **kwargs})

    def start(self, **kwargs):
        return self.client.post(self.url, {"play_mode": "DEEP_TALK", **kwargs}, format="json")

    def test_nonowner_friend_can_start_deep_and_question_is_sent_in_same_chat(self):
        with patch("apps.game.services.random.random", return_value=0.2):
            response = self.start()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["session"]["play_mode"], "DEEP_TALK")
        self.assertEqual(response.data["session"]["max_intensity"], 3)
        self.assertEqual(response.data["turn"]["status"], "ANSWERING")
        self.assertEqual(response.data["turn"]["prompt"]["id"], self.bold.pk)
        self.assertEqual(Conversation.objects.count(), 1)
        message = Message.objects.get(type="GAME_PROMPT")
        self.assertEqual(message.conversation_id, self.room.pk)
        self.assertEqual(message.meta["play_mode"], "DEEP_TALK")

    def test_weight_boundary_and_private_path(self):
        with patch("apps.game.services.random.random", return_value=0.7):
            response = self.start()
        self.assertEqual(response.data["turn"]["prompt"]["id"], self.private.pk)

    def test_fallback_no_repeat_and_exhaustion_does_not_end_conversation(self):
        with patch("apps.game.services.random.random", return_value=0):
            response = self.start()
            session = GameSession.objects.get(pk=response.data["session"]["id"])
            first = game.current_turn(session)
            game.skip(User.objects.get(pk=first.player_id), first.pk)
            second = game.current_turn(session)
            self.assertEqual(second.prompt_id, self.private.pk)
            game.skip(User.objects.get(pk=second.player_id), second.pk)
        self.assertEqual(Message.objects.filter(type="GAME_PROMPT").count(), 2)
        session.refresh_from_db(); self.assertEqual(set(session.used_prompt_ids), {self.bold.pk, self.private.pk})
        self.assertEqual(session.status, "ACTIVE")
        self.room.refresh_from_db(); self.assertEqual(self.room.status, "ACTIVE")
        turn = game.current_turn(session)
        self.assertEqual(turn.status, "CHOOSING")
        with self.assertRaisesMessage(Exception, "فقط سؤال"):
            game.choose(User.objects.get(pk=turn.player_id), turn.pk, "DARE")

    def test_private_only_bank_still_works(self):
        self.bold.is_active = False; self.bold.save()
        with patch("apps.game.services.random.random", return_value=0):
            response = self.start()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["turn"]["prompt"]["id"], self.private.pk)

    def test_deep_requires_accepted_friendship_even_for_room_owner(self):
        self.friend.status = "PENDING"; self.friend.save()
        self.client.force_authenticate(self.a)
        self.assertEqual(self.start().status_code, 403)
        self.assertFalse(GameSession.objects.exists())

    def test_deep_rejects_group_minor_blocked_and_nonparticipant(self):
        self.client.force_authenticate(self.c)
        self.assertEqual(self.start().status_code, 403)
        self.client.force_authenticate(self.a)
        self.room.max_players = 5; self.room.save()
        self.assertEqual(self.start().status_code, 403)
        self.room.max_players = 2; self.room.save()
        self.b.birth_date = date.today().replace(year=date.today().year - 10); self.b.save()
        self.assertEqual(self.start().status_code, 403)
        self.b.birth_date = date(1998, 1, 1); self.b.save()
        Block.objects.create(blocker=self.b, blocked=self.a)
        self.assertEqual(self.start().status_code, 403)
        self.assertFalse(GameSession.objects.exists())

    def test_nonowner_friend_can_restart_classic_and_stale_retry_cannot_end_new_game(self):
        first = self.client.post(self.url, {}, format="json")
        self.assertEqual(first.status_code, 201)
        first_id = first.data["session"]["id"]
        self.assertEqual(self.start().status_code, 409)
        response = self.start(replace_session_id=first_id)
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.data["session"]["id"], first_id)
        self.assertEqual(GameSession.objects.get(pk=first_id).status, "ENDED")
        self.assertEqual(self.start(replace_session_id=first_id).status_code, 409)
        self.assertEqual(GameSession.objects.filter(status="ACTIVE").count(), 1)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_failed_deep_start_does_not_end_current_game(self):
        first = self.client.post(self.url, {}, format="json")
        Prompt.objects.filter(category__in=["BOLD", "FUNNY"]).update(is_active=False)
        self.assertEqual(self.start(replace_session_id=first.data["session"]["id"]).status_code, 409)
        self.assertEqual(game.active_session(self.room.pk).pk, first.data["session"]["id"])

    def test_nonfriend_nonowner_cannot_start_classic_and_invalid_input_is_400(self):
        self.friend.delete()
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 403)
        self.client.force_authenticate(self.a)
        self.assertEqual(self.client.post(self.url, {"max_intensity": "wrong"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.url, {"play_mode": "invented"}, format="json").status_code, 400)

    def test_nonowner_friend_can_end_deep_game(self):
        self.assertEqual(self.start().status_code, 201)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(game.active_session(self.room.pk))

    def test_normal_chat_answer_and_confirmation_advance_deep_question(self):
        from apps.chat import services as chat
        result = self.start()
        session = GameSession.objects.get(pk=result.data["session"]["id"])
        turn = game.current_turn(session)
        player = User.objects.get(pk=turn.player_id)
        other = self.a if player.pk == self.b.pk else self.b
        chat.post_message(conversation=self.room, sender=player, body="a normal chat answer", client_id="deep-answer")
        turn.refresh_from_db()
        self.assertEqual(turn.status, "CONFIRMING")
        game.confirm(other, turn.pk)
        next_turn = game.current_turn(session)
        self.assertEqual(next_turn.status, "ANSWERING")
        self.assertNotEqual(next_turn.prompt_id, turn.prompt_id)
        self.assertEqual(next_turn.player_id, other.pk)
