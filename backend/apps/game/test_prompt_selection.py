from django.test import TestCase

from apps.chat.models import Conversation, Message, Participant
from apps.core.errors import DomainError
from apps.game import services as game
from apps.game.models import GameSession, Prompt, Turn, TurnStatus
from apps.users.models import User


class PromptSelectionTests(TestCase):
    def setUp(self):
        self.players = [User.objects.create_user(username=f"player{i}") for i in range(2)]
        self.room = Conversation.objects.create(type="DIRECT", owner=self.players[0])
        Participant.objects.bulk_create([
            Participant(conversation=self.room, user=user) for user in self.players
        ])
        self.session = GameSession.objects.create(
            conversation=self.room, turn_order=[u.pk for u in self.players],
            category="FRIENDLY", max_intensity=1,
        )
        self.turn = Turn.objects.create(session=self.session, player=self.players[0], index=0)

    def prompt(self, text, **overrides):
        return Prompt.objects.create(**{
            "text": text, "type": "TRUTH", "category": "FRIENDLY",
            "intensity": 1, "review_status": "APPROVED", **overrides,
        })

    def test_no_repeat_across_players_skips_rounds_and_state_reload(self):
        prompts = [self.prompt(f"سؤال تازهٔ {i}") for i in range(3)]
        shown = []
        turn = self.turn
        for _ in range(3):
            player = User.objects.get(pk=turn.player_id)
            selected = game.choose(player, turn.pk, "TRUTH")
            shown.append(selected.prompt_id)
            game.skip(player, turn.pk)
            self.session.refresh_from_db()
            turn = game.current_turn(self.session)

        self.assertCountEqual(shown, [p.pk for p in prompts])
        self.assertEqual(len(set(shown)), 3)
        self.assertCountEqual(self.session.used_prompt_ids, shown)
        before = Message.objects.filter(type="GAME_PROMPT").count()
        with self.assertRaises(DomainError) as error:
            game.choose(User.objects.get(pk=turn.player_id), turn.pk, "TRUTH")
        self.assertEqual(error.exception.code, "prompts_exhausted")
        turn.refresh_from_db()
        self.assertEqual(turn.status, TurnStatus.CHOOSING)
        self.assertIsNone(turn.prompt_id)
        self.assertEqual(Message.objects.filter(type="GAME_PROMPT").count(), before)

        dare = self.prompt("یک داستان کوتاه بساز.", type="DARE")
        chosen = game.choose(User.objects.get(pk=turn.player_id), turn.pk, "DARE")
        self.assertEqual(chosen.prompt_id, dare.pk)

    def test_exhaustion_never_relaxes_moderation_or_session_filters(self):
        used = self.prompt("سؤال قبلی")
        self.session.used_prompt_ids = [used.pk]
        self.session.save(update_fields=["used_prompt_ids"])
        for index, overrides in enumerate([
            {"review_status": "PENDING"}, {"review_status": "REJECTED"},
            {"is_active": False}, {"intensity": 3},
            {"category": "BOLD"}, {"min_players": 3},
        ]):
            self.prompt(f"نباید نمایش داده شود {index}", **overrides)
        with self.assertRaises(DomainError) as error:
            game.choose(self.players[0], self.turn.pk, "TRUTH")
        self.assertEqual(error.exception.code, "prompts_exhausted")
        self.assertFalse(Message.objects.filter(type="GAME_PROMPT").exists())

    def test_new_session_can_use_question_from_previous_game(self):
        prompt = self.prompt("سؤال مشترک بین دو بازی")
        game.choose(self.players[0], self.turn.pk, "TRUTH")
        game.stop_game(self.players[0], self.room.pk)
        session = game.start_game(self.players[0], self.room)
        turn = game.current_turn(session)
        chosen = game.choose(User.objects.get(pk=turn.player_id), turn.pk, "TRUTH")
        self.assertEqual(chosen.prompt_id, prompt.pk)

    def test_empty_bank_keeps_turn_waiting_and_does_not_add_message(self):
        with self.assertRaises(DomainError) as error:
            game.choose(self.players[0], self.turn.pk, "TRUTH")
        self.assertEqual(error.exception.code, "no_prompts")
        self.turn.refresh_from_db()
        self.assertEqual(self.turn.status, TurnStatus.CHOOSING)
        self.assertFalse(Message.objects.exists())
