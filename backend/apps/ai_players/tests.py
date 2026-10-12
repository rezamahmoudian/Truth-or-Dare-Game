import json
import uuid
from datetime import date, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chat import services as chat
from apps.chat.models import Conversation, Message, Participant
from apps.chat.payloads import message_payload
from apps.core.errors import DomainError
from apps.game import services as game
from apps.game.models import Prompt, TurnStatus
from apps.matchmaking import services as matchmaking
from apps.matchmaking.models import MatchMode, MatchTicket
from apps.users.models import Block, User
from apps.users.payloads import person_payload

from . import client, readiness, services, tasks
from .models import AIConversation, AIEncounter, AIRequest, AISettings, DailyUsage, Persona


@override_settings(AI_PLAYERS_ENABLED=True, OPENAI_API_KEY="test-only", AI_DAILY_REQUEST_LIMIT=100,
                   OPENAI_BASE_URL="https://api.openai.com/v1", OPENAI_EXTRA_HEADERS={},
                   AI_USER_DAILY_REQUEST_LIMIT=20,
                   AI_MESSAGE_BATCH_SECONDS=0,
                   CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class AIPlayerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.readiness_patch = patch("apps.ai_players.readiness.ready_for_ticket", return_value=True)
        self.readiness_patch.start()
        self.addCleanup(self.readiness_patch.stop)
        self.human = User.objects.create_user(username="human", display_name="بازیکن", gender="M", birth_date=date(1995, 1, 1))
        self.persona = Persona.objects.create(first_name="رها", last_name="نیک‌منش", age=24, city="شیراز",
            bio="شخصیت داستانی", interests="موسیقی", personality="شوخ", speaking_style="خودمانی")
        self.mode = MatchMode.objects.create(key="ai-test", title="هوش مصنوعی", is_ai=True)
        self.client = APIClient()
        self.client.force_authenticate(self.human)
        for target in ["apps.chat.broadcast.to_users", "apps.chat.broadcast.to_conversation", "apps.ai_players.services.dispatch",
                       "apps.ai_players.services.schedule_delivery",
                       "apps.ai_players.services.schedule_silence_continuation"]:
            mock = patch(target)
            mock.start()
            self.addCleanup(mock.stop)

    def matched(self):
        ticket = matchmaking.enqueue(self.human, self.mode.key, ai_consent=True)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(services.match_ticket(ticket))
        ticket.refresh_from_db()
        return AIConversation.objects.select_related("persona__user", "human", "conversation").get(pk=ticket.conversation_id)

    @staticmethod
    def reply(persona, context, action):
        return {"action": action, "text": "من در داستان بازی موسیقی را دوست دارم.", "choice": "TRUTH"}, {"input_tokens": 100, "output_tokens": 30}

    def run_reply(self, state):
        with patch("apps.ai_players.tasks.reply_delay_seconds", return_value=0), patch("apps.ai_players.client.generate", side_effect=self.reply) as generate, self.captureOnCommitCallbacks(execute=True):
            tasks.respond(str(state.pk))
            for request in AIRequest.objects.filter(conversation=state, status="READY"):
                tasks.deliver(str(request.pk))
        state.refresh_from_db()
        return generate

    def test_reply_delay_is_random_bounded_and_increases_with_length(self):
        with patch("apps.ai_players.tasks.random.uniform", return_value=0.85):
            short_min = tasks.reply_delay_seconds({"action": "chat", "text": "سلام"})
            long_min = tasks.reply_delay_seconds({"action": "chat", "text": "الف " * 100})
        with patch("apps.ai_players.tasks.random.uniform", return_value=1.15):
            short_max = tasks.reply_delay_seconds({"action": "chat", "text": "سلام"})
            long_max = tasks.reply_delay_seconds({"action": "chat", "text": "الف " * 100})
        self.assertGreaterEqual(short_min, 0.5)
        self.assertLess(short_max, 1.5)
        self.assertGreater(short_max, short_min)
        self.assertGreater(long_min, short_max)
        self.assertGreater(long_max, long_min)
        self.assertLessEqual(long_max, 8)

    @override_settings(AI_HISTORY_MESSAGES=2)
    def test_full_unanswered_batch_survives_history_limit(self):
        state = self.matched()
        Message.objects.create(conversation=state.conversation, sender=self.human, body="سؤال قدیمی پاسخ داده شده")
        Message.objects.create(conversation=state.conversation, sender=self.persona.user, body="جواب قبلی")
        texts = ["سؤال مهم " + "الف" * 1500] + [f"ادامه {i}" for i in range(30)]
        Message.objects.bulk_create(Message(conversation=state.conversation, sender=self.human, body=text) for text in texts)
        Message.objects.create(conversation=state.conversation, sender=self.human, body="حذف‌شده", is_deleted=True)
        _, _, context = services.snapshot(state)
        self.assertEqual([m["text"] for m in context["pending_user_messages"]], texts)
        self.assertEqual(len(context["history"]), 2)
        self.run_reply(state)
        action, _, context = services.snapshot(state)
        self.assertEqual(action, "wait")
        self.assertEqual(context["pending_user_messages"], [])
        self.assertEqual(Message.objects.filter(sender=self.persona.user).count(), 2)

    @override_settings(AI_MESSAGE_BATCH_SECONDS=1.5)
    def test_burst_waits_for_pause_then_gets_one_reply(self):
        state = self.matched()
        now = timezone.now()
        with patch("apps.ai_players.client.generate", side_effect=self.reply) as generate, patch(
            "apps.ai_players.tasks.reply_delay_seconds", return_value=0
        ), patch("apps.ai_players.services.dispatch") as dispatch:
            with patch("django.utils.timezone.now", return_value=now), self.captureOnCommitCallbacks(execute=True):
                chat.post_message(conversation=state.conversation, sender=self.human, body="اهل کجایی؟")
                tasks.respond(str(state.pk))
            dispatch.assert_any_call(str(state.pk), eta=now + timedelta(seconds=1.5))
            self.assertFalse(generate.called)
            with patch("django.utils.timezone.now", return_value=now + timedelta(seconds=1)), self.captureOnCommitCallbacks(execute=True):
                chat.post_message(conversation=state.conversation, sender=self.human, body="چه آهنگی دوست داری؟")
            with patch("django.utils.timezone.now", return_value=now + timedelta(seconds=1.5)), self.captureOnCommitCallbacks(execute=True):
                tasks.respond(str(state.pk))
            dispatch.assert_any_call(str(state.pk), eta=now + timedelta(seconds=2.5))
            self.assertFalse(generate.called)
            with patch("django.utils.timezone.now", return_value=now + timedelta(seconds=2.5)), self.captureOnCommitCallbacks(execute=True):
                tasks.respond(str(state.pk))
                request = AIRequest.objects.get(status="READY")
                tasks.respond(str(state.pk))
                tasks.deliver(str(request.pk))
                tasks.deliver(str(request.pk))
                tasks.respond(str(state.pk))
        self.assertEqual(generate.call_count, 1)
        self.assertEqual([m["text"] for m in generate.call_args.args[1]["pending_user_messages"]],
                         ["اهل کجایی؟", "چه آهنگی دوست داری؟"])
        self.assertEqual(Message.objects.filter(sender=self.persona.user).count(), 1)

    def test_more_messages_replace_unsent_draft_with_one_combined_reply(self):
        state = self.matched()
        with self.captureOnCommitCallbacks(execute=True):
            chat.post_message(conversation=state.conversation, sender=self.human, body="سؤال اول")
        draft = self.prepare_delayed_reply(state)
        with self.captureOnCommitCallbacks(execute=True):
            for text in ["سؤال دوم", "بی‌خیال سؤال اول، فقط دومی"]:
                chat.post_message(conversation=state.conversation, sender=self.human, body=text)
        generate = self.run_reply(state)
        self.assertEqual([m["text"] for m in generate.call_args.args[1]["pending_user_messages"]],
                         ["سؤال اول", "سؤال دوم", "بی‌خیال سؤال اول، فقط دومی"])
        draft.refresh_from_db()
        self.assertEqual(draft.status, "STALE")
        self.assertEqual(draft.delivery_payload, {})
        tasks.deliver(str(draft.pk))
        self.run_reply(state)
        self.assertEqual(Message.objects.filter(sender=self.persona.user).count(), 1)

    def test_messages_during_generation_are_included_in_replacement(self):
        state = self.matched()
        with self.captureOnCommitCallbacks(execute=True):
            chat.post_message(conversation=state.conversation, sender=self.human, body="سؤال اول")
        def another_message(*args):
            with self.captureOnCommitCallbacks(execute=True):
                chat.post_message(conversation=state.conversation, sender=self.human, body="سؤال دوم")
            return self.reply(*args)
        with patch("apps.ai_players.client.generate", side_effect=another_message):
            tasks.respond(str(state.pk))
        self.assertEqual(AIRequest.objects.get().status, "STALE")
        self.assertFalse(Message.objects.filter(sender=self.persona.user).exists())
        generate = self.run_reply(state)
        self.assertEqual([m["text"] for m in generate.call_args.args[1]["pending_user_messages"]],
                         ["سؤال اول", "سؤال دوم"])
        self.assertEqual(Message.objects.filter(sender=self.persona.user).count(), 1)

    def prepare_delayed_reply(self, state):
        with patch("apps.ai_players.tasks.reply_delay_seconds", return_value=10), patch(
            "apps.ai_players.client.generate", side_effect=self.reply
        ), self.captureOnCommitCallbacks(execute=True):
            tasks.respond(str(state.pk))
        return AIRequest.objects.get(conversation=state, status="READY")

    def test_delayed_reply_is_durable_not_early_and_sent_only_once(self):
        state = self.matched()
        request = self.prepare_delayed_reply(state)
        self.assertFalse(Message.objects.filter(sender=self.persona.user).exists())
        with patch("apps.ai_players.client.generate") as generate:
            tasks.respond(str(state.pk))
            self.assertFalse(generate.called)
        with patch("django.utils.timezone.now", return_value=request.deliver_at - timedelta(seconds=1)):
            tasks.deliver(str(request.pk))
        self.assertFalse(Message.objects.filter(sender=self.persona.user).exists())
        with patch("django.utils.timezone.now", return_value=request.deliver_at):
            with patch("apps.ai_players.services.schedule_delivery") as schedule:
                tasks.recover_pending()
                schedule.assert_called_once_with(request.pk, request.deliver_at)
            tasks.deliver(str(request.pk))
            tasks.deliver(str(request.pk))
        self.assertEqual(Message.objects.filter(sender=self.persona.user).count(), 1)
        request.refresh_from_db()
        self.assertEqual(request.status, "DONE")
        self.assertEqual(request.delivery_payload, {})
        self.assertEqual(DailyUsage.objects.get(user_key=self.human.pk).requests, 1)

    def test_delayed_reply_discarded_if_chat_changes_before_delivery(self):
        for reason in ("new_message", "before_notify", "closed", "expired", "blocked", "persona_edit"):
            with self.subTest(reason=reason):
                state = self.matched()
                request = self.prepare_delayed_reply(state)
                if reason == "new_message":
                    with self.captureOnCommitCallbacks(execute=True):
                        chat.post_message(conversation=state.conversation, sender=self.human, body="سؤال تازه")
                elif reason == "before_notify":
                    # A message can commit just before its notification callback runs.
                    Message.objects.create(conversation=state.conversation, sender=self.human, body="پیام تازه")
                elif reason == "closed":
                    chat.close_room(self.human, state.conversation)
                elif reason == "expired":
                    AIConversation.objects.filter(pk=state.pk).update(expires_at=timezone.now())
                elif reason == "blocked":
                    Block.objects.create(blocker=self.human, blocked=self.persona.user)
                else:
                    self.persona.speaking_style = "لحن تازه"
                    self.persona.save()
                with patch("django.utils.timezone.now", return_value=request.deliver_at):
                    tasks.deliver(str(request.pk))
                request.refresh_from_db()
                self.assertEqual(request.status, "STALE")
                self.assertFalse(Message.objects.filter(sender=self.persona.user).exists())
                state.conversation.delete()
                Block.objects.all().delete()
                # Reset this subtest's fixture, including independent lifetime history.
                AIEncounter.objects.all().delete()

    def test_persona_profile_and_validation(self):
        self.persona.user.refresh_from_db()
        self.assertTrue(self.persona.user.is_ai)
        self.assertFalse(self.persona.user.has_usable_password())
        public = person_payload(self.persona.user)
        self.assertTrue(public["is_ai"])
        self.assertEqual(public["ai_profile"]["city"], "شیراز")
        self.assertNotIn("speaking_style", json.dumps(public))
        self.persona.age = 17
        with self.assertRaises(ValidationError):
            self.persona.full_clean()

    def test_seed_preserves_edits(self):
        call_command("seed_ai_personas", verbosity=0)
        self.persona.bio = "ویرایش مدیر"
        self.persona.save()
        call_command("seed_ai_personas", verbosity=0)
        self.assertEqual(Persona.objects.count(), 3)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.bio, "ویرایش مدیر")

    def test_consent_and_disabled_provider(self):
        self.assertEqual(self.client.post("/api/match/", {"mode": self.mode.key}, format="json").status_code, 400)
        with override_settings(AI_PLAYERS_ENABLED=False):
            result = self.client.post("/api/match/", {"mode": self.mode.key, "ai_consent": True}, format="json")
            self.assertEqual(result.status_code, 503)
        self.assertFalse(MatchTicket.objects.exists())
        self.assertEqual(self.client.get("/api/ai/personas/").data["personas"][0]["ai_profile"]["age"], 24)

    def test_matching_is_explicit_block_aware_and_idempotent(self):
        human_mode = MatchMode.objects.create(key="human", title="بازیکن واقعی")
        other = User.objects.create_user(username="other", display_name="بازیکن دوم", gender="F", birth_date=date(1998, 1, 1))
        a = matchmaking.enqueue(self.human, self.mode.key, ai_consent=True)
        b = matchmaking.enqueue(other, human_mode.key)
        self.assertFalse(matchmaking._compatible(a, b))
        self.assertTrue(services.match_ticket(a))
        self.assertFalse(services.match_ticket(a))
        a.refresh_from_db()
        self.assertIsNone(a.conversation.code)
        self.assertEqual(a.conversation.owner_id, self.human.pk)
        self.assertEqual(a.conversation.active_participants.count(), 2)
        self.assertFalse(Message.objects.filter(conversation=a.conversation).exists())
        with self.assertRaises(DomainError) as exhausted:
            matchmaking.enqueue(self.human, self.mode.key, ai_consent=True)
        self.assertEqual(exhausted.exception.code, "ai_no_persona")
        self.assertEqual(AIConversation.objects.count(), 1)
        Block.objects.create(blocker=self.human, blocked=self.persona.user)
        with self.assertRaises(DomainError):
            matchmaking.enqueue(self.human, self.mode.key, ai_consent=True)

    def test_reply_once_and_no_ai_self_loop(self):
        state = self.matched()
        self.run_reply(state)
        generate = self.run_reply(state)
        self.assertFalse(generate.called)
        self.assertEqual(Message.objects.filter(sender=self.persona.user).count(), 1)
        msg = Message.objects.get(sender=self.persona.user)
        self.assertTrue(message_payload(msg)["sender"]["is_ai"])
        self.assertEqual(AIRequest.objects.get().output_tokens, 30)
        with self.captureOnCommitCallbacks(execute=True):
            chat.post_message(conversation=state.conversation, sender=self.human, body="سلام")
        self.run_reply(state)
        self.assertEqual(Message.objects.filter(sender=self.persona.user).count(), 2)

    def test_old_welcome_cleanup_preserves_player_and_ai_messages(self):
        state = self.matched()
        old_welcome = (
            "رها یک شخصیت داستانی هوش مصنوعی است. پیام‌های متنی این گفتگو برای تولید پاسخ "
            "به OpenAI فرستاده می‌شوند. این شخصیت فقط حقیقت انتخاب می‌کند. "
            "هر وقت آماده بودی بازی را شروع کن."
        )
        welcome = Message.objects.create(conversation_id=state.pk, type="SYSTEM", body=old_welcome)
        human = Message.objects.create(conversation_id=state.pk, sender=self.human, body=old_welcome)
        ai = Message.objects.create(conversation_id=state.pk, sender=self.persona.user, body=old_welcome)
        notice = Message.objects.create(conversation_id=state.pk, type="SYSTEM", body="گفتگو بسته شد.")
        migration = import_module("apps.ai_players.migrations.0005_remove_verbose_welcome")
        migration.remove_verbose_welcome(apps, SimpleNamespace(connection=connection))
        self.assertFalse(Message.objects.filter(pk=welcome.pk).exists())
        self.assertEqual(Message.objects.filter(pk__in=[human.pk, ai.pk, notice.pk]).count(), 3)

    def test_entire_game_cycle_waits_for_human_confirmation(self):
        state = self.matched()
        self.run_reply(state)
        Prompt.objects.create(type="TRUTH", text="چه موسیقی دوست داری؟", review_status="APPROVED", is_active=True)
        Prompt.objects.create(type="TRUTH", text="چه فیلمی دوست داری؟", review_status="APPROVED", is_active=True)
        Prompt.objects.create(type="TRUTH", text="نباید انتخاب شود", review_status="PENDING", is_active=True)
        with patch("apps.game.services.random.shuffle", side_effect=lambda ids: ids.sort(reverse=True)), self.captureOnCommitCallbacks(execute=True):
            session = game.start_game(self.human, state.conversation)
        turn = game.current_turn(session)
        self.assertEqual(turn.player_id, self.persona.user_id)
        self.run_reply(state)
        turn.refresh_from_db()
        self.assertEqual(turn.status, TurnStatus.ANSWERING)
        self.assertEqual(turn.prompt.review_status, "APPROVED")
        self.run_reply(state)
        turn.refresh_from_db()
        self.assertEqual(turn.status, TurnStatus.CONFIRMING)
        self.run_reply(state)
        self.assertEqual(session.turns.count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            game.confirm(self.human, turn.pk)
        session.refresh_from_db()
        turn = game.current_turn(session)
        self.assertEqual(turn.player_id, self.human.pk)
        with self.captureOnCommitCallbacks(execute=True):
            game.choose(self.human, turn.pk, "TRUTH")
            game.answer(self.human, turn.pk, "راک")
        self.run_reply(state)
        turn.refresh_from_db()
        self.assertEqual(turn.status, TurnStatus.DONE)
        self.assertEqual(game.current_turn(session).player_id, self.persona.user_id)

        # Both approved questions are spent. The truth-only AI skips instead
        # of recycling one, choosing a dare, or getting stuck on a failed job.
        ai_turn = game.current_turn(session)
        prompt_count = Message.objects.filter(conversation=state.conversation, type="GAME_PROMPT").count()
        self.run_reply(state)
        ai_turn.refresh_from_db()
        self.assertEqual(ai_turn.status, TurnStatus.SKIPPED)
        self.assertEqual(game.current_turn(session).player_id, self.human.pk)
        self.assertEqual(Message.objects.filter(conversation=state.conversation, type="GAME_PROMPT").count(), prompt_count)
        self.assertTrue(Message.objects.filter(conversation=state.conversation, meta__game="prompts_exhausted").exists())

    def test_confirming_answer_can_have_chat_before_ai_confirms(self):
        state = self.matched()
        Prompt.objects.create(
            type="TRUTH", text="چه موسیقی دوست داری؟", review_status="APPROVED", is_active=True
        )
        with patch("apps.game.services.random.shuffle", side_effect=lambda ids: ids.sort()), self.captureOnCommitCallbacks(execute=True):
            session = game.start_game(self.human, state.conversation)
            turn = game.current_turn(session)
            self.assertEqual(turn.player_id, self.human.pk)
            game.choose(self.human, turn.pk, "TRUTH")
            game.answer(self.human, turn.pk, "راک")
        state.refresh_from_db()
        action, _, context = services.snapshot(state)
        self.assertEqual(action, "confirm")
        self.assertEqual(context["allowed_actions"], ["chat", "confirm"])

        def run_action(reply):
            with patch("apps.ai_players.tasks.reply_delay_seconds", return_value=0), patch(
                "apps.ai_players.client.generate", return_value=(reply, {"output_tokens": 4})
            ), self.captureOnCommitCallbacks(execute=True):
                tasks.respond(str(state.pk))
                for request in AIRequest.objects.filter(conversation=state, status="READY"):
                    tasks.deliver(str(request.pk))

        run_action({"action": "chat", "text": "منم راک دوست دارم، مخصوصاً وقتی حال آدم گرفته‌ست", "choice": "TRUTH"})
        turn.refresh_from_db()
        self.assertEqual(turn.status, TurnStatus.CONFIRMING)
        self.assertEqual(Message.objects.filter(conversation=state.conversation, sender=self.persona.user).count(), 1)
        Message.objects.bulk_create([
            Message(conversation=state.conversation, sender=self.persona.user, body="ادامهٔ کوتاه اول"),
            Message(conversation=state.conversation, sender=self.persona.user, body="ادامهٔ کوتاه دوم"),
        ])
        _, _, capped_context = services.snapshot(state)
        self.assertEqual(capped_context["confirming_chat_messages"], 3)
        self.assertEqual(capped_context["allowed_actions"], ["confirm"])

        with self.captureOnCommitCallbacks(execute=True):
            chat.post_message(conversation=state.conversation, sender=self.human, body="دقیقاً، تو چه خواننده‌ای رو بیشتر گوش می‌دی؟")
        run_action({"action": "confirm", "text": "آره، انتخاب خوبیه", "choice": "TRUTH"})
        turn.refresh_from_db()
        self.assertEqual(turn.status, TurnStatus.DONE)

    def test_provider_schema_allows_chat_or_confirm_when_context_allows_both(self):
        response = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": '{"action":"chat","text":"چه انتخاب خوبی","choice":"TRUTH"}'}]}]}
        context = {"allowed_actions": ["chat", "confirm"], "history": []}
        with patch("apps.ai_players.client.urlopen") as http:
            http.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            reply, _ = client.generate(self.persona, context, "confirm")
        body = json.loads(http.call_args.args[0].data)
        self.assertEqual(body["text"]["format"]["schema"]["properties"]["action"]["enum"], ["chat", "confirm"])
        self.assertEqual(reply["action"], "chat")

    def test_silence_continuation_confirms_after_ai_chat(self):
        state = self.matched()
        Prompt.objects.create(
            type="TRUTH", text="چه موسیقی دوست داری؟", review_status="APPROVED", is_active=True
        )
        with patch("apps.game.services.random.shuffle", side_effect=lambda ids: ids.sort()), self.captureOnCommitCallbacks(execute=True):
            session = game.start_game(self.human, state.conversation)
            turn = game.current_turn(session)
            game.choose(self.human, turn.pk, "TRUTH")
            game.answer(self.human, turn.pk, "راک")
        state.refresh_from_db()
        reply = {"action": "chat", "text": "چه انتخاب خوبی", "choice": "TRUTH"}
        with patch("apps.ai_players.tasks.reply_delay_seconds", return_value=0), patch(
            "apps.ai_players.client.generate", return_value=(reply, {})
        ), self.captureOnCommitCallbacks(execute=True):
            tasks.respond(str(state.pk))
            request = AIRequest.objects.get(conversation=state, status="READY")
            tasks.deliver(str(request.pk))
        state.refresh_from_db()
        message = Message.objects.get(conversation=state.conversation, sender=self.persona.user)
        tasks.continue_after_silence(str(state.pk), state.revision, message.pk)
        turn.refresh_from_db()
        self.assertEqual(turn.status, TurnStatus.DONE)

    def test_context_is_scoped_and_excludes_deleted_text(self):
        state = self.matched()
        elsewhere = Conversation.objects.create(type="ROOM")
        Message.objects.create(conversation=elsewhere, sender=self.human, body="SECRET OTHER ROOM")
        Message.objects.create(conversation=state.conversation, sender=self.human, body="DELETED", is_deleted=True)
        Message.objects.create(conversation=state.conversation, sender=self.human, type="ATTACHMENT", attachment="private/file", attachment_info={"kind": "voice"})
        _, _, context = services.snapshot(state)
        encoded = json.dumps(context)
        self.assertNotIn("SECRET", encoded)
        self.assertNotIn("DELETED", encoded)
        self.assertNotIn("private/file", encoded)
        self.assertIn("voice", encoded)

    def test_inflight_close_discards_response(self):
        state = self.matched()
        def late(*args):
            chat.close_room(self.human, state.conversation)
            return self.reply(*args)
        with patch("apps.ai_players.client.generate", side_effect=late):
            tasks.respond(str(state.pk))
        self.assertFalse(Message.objects.filter(sender=self.persona.user).exists())
        self.assertEqual(AIRequest.objects.get().status, "STALE")

    def test_inflight_new_message_and_persona_edit_discard_response(self):
        state = self.matched()
        def changed(*args):
            services.notify(state.pk)
            return self.reply(*args)
        with patch("apps.ai_players.client.generate", side_effect=changed):
            tasks.respond(str(state.pk))
        self.assertFalse(Message.objects.filter(sender=self.persona.user).exists())
        self.run_reply(state)
        self.assertEqual(Message.objects.filter(sender=self.persona.user).count(), 1)

    def test_inflight_skipped_turn_and_persona_edit_are_stale(self):
        state = self.matched()
        with patch("apps.game.services.random.shuffle", side_effect=lambda ids: ids.sort(reverse=True)), self.captureOnCommitCallbacks(execute=True):
            session = game.start_game(self.human, state.conversation)
        turn = game.current_turn(session)
        def skip_during_request(*args):
            game.force_next(self.human, turn.pk)
            return self.reply(*args)
        with patch("apps.ai_players.client.generate", side_effect=skip_during_request):
            tasks.respond(str(state.pk))
        self.assertEqual(AIRequest.objects.get().status, "STALE")
        self.assertFalse(Message.objects.filter(sender=self.persona.user).exists())
        def edit_during_request(*args):
            self.persona.speaking_style = "لحن تازه"
            self.persona.save()
            return self.reply(*args)
        with patch("apps.ai_players.client.generate", side_effect=edit_during_request):
            tasks.respond(str(state.pk))
        self.assertEqual(AIRequest.objects.filter(status="STALE").count(), 2)
        self.assertEqual(game.current_turn(session).player_id, self.human.pk)

    def test_duplicate_worker_and_expired_lease(self):
        state = self.matched()
        def nested(*args):
            tasks.respond(str(state.pk))
            return self.reply(*args)
        with patch("apps.ai_players.client.generate", side_effect=nested) as generate:
            tasks.respond(str(state.pk))
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(AIRequest.objects.count(), 1)
        services.notify(state.pk)
        AIConversation.objects.filter(pk=state.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
        self.assertIn(state.pk, list(services.pending_ids()))

    def test_daily_limits_and_provider_retries(self):
        state = self.matched()
        with patch("apps.ai_players.client.generate", side_effect=client.ProviderError("http_429", True)) as generate:
            tasks.respond(str(state.pk))
            tasks.respond(str(state.pk))
            self.assertEqual(generate.call_count, 1)
            for _ in range(2):
                AIConversation.objects.filter(pk=state.pk).update(retry_at=timezone.now() - timedelta(seconds=1))
                tasks.respond(str(state.pk))
            self.assertEqual(generate.call_count, 3)
        state.refresh_from_db()
        self.assertEqual(state.revision, state.handled_revision)
        self.assertFalse(Message.objects.filter(meta__has_key="ai_error").exists())
        self.assertEqual(state.last_error, "http_429")
        services.notify(state.pk)
        with patch("apps.ai_players.client.generate", side_effect=client.ProviderError("http_429", True)):
            tasks.respond(str(state.pk))
        state.refresh_from_db()
        self.assertEqual(state.failures, 1)
        self.assertIsNotNone(state.retry_at)
        AIConversation.objects.filter(pk=state.pk).update(retry_at=None)
        with override_settings(AI_USER_DAILY_REQUEST_LIMIT=4):
            services.notify(state.pk)
            generate = self.run_reply(state)
            self.assertFalse(generate.called)
            self.assertEqual(DailyUsage.objects.get(user_key=self.human.pk).requests, 4)

    def test_block_departure_and_disabled_persona_stop_work(self):
        state = self.matched()
        Block.objects.create(blocker=self.human, blocked=self.persona.user)
        self.assertFalse(self.run_reply(state).called)
        Block.objects.all().delete()
        services.notify(state.pk)
        Participant.objects.filter(conversation_id=state.pk, user=self.human).update(left_at=timezone.now())
        self.assertFalse(self.run_reply(state).called)
        Participant.objects.filter(conversation_id=state.pk, user=self.human).update(left_at=None)
        services.notify(state.pk)
        Persona.objects.filter(pk=self.persona.pk).update(is_active=False)
        self.assertFalse(self.run_reply(state).called)

    def test_retry_requires_membership(self):
        state = self.matched()
        outsider = User.objects.create_user(username="outsider")
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.post(f"/api/conversations/{state.pk}/ai/retry/").status_code, 403)

    def test_no_provider_request_without_configuration(self):
        state = self.matched()
        with override_settings(OPENAI_API_KEY=""):
            self.assertFalse(self.run_reply(state).called)
        self.assertFalse(AIRequest.objects.exists())

    def test_match_requires_fresh_successful_probe_for_each_ticket(self):
        self.readiness_patch.stop()
        ticket = self.fallback_ticket()
        self.make_due(ticket)
        with patch.object(readiness.probe_ticket, "delay") as queued, self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(services.match_ticket(ticket))
            self.assertFalse(services.match_ticket(ticket))
        queued.assert_called_once()
        self.assertFalse(AIConversation.objects.exists())
        with patch("apps.ai_players.client.generate", side_effect=self.reply) as generate:
            readiness.probe_ticket(*queued.call_args.args)
            readiness.probe_ticket(*queued.call_args.args)
        generate.assert_called_once()
        self.assertTrue(services.match_ticket(ticket))
        self.assertEqual(AIConversation.objects.count(), 1)
        again = matchmaking.enqueue(self.human, ticket.mode.key)
        self.make_due(again)
        Persona.objects.create(first_name="تازه", last_name="نمونه", age=25, city="شیراز",
            bio="شخصیت داستانی", interests="هنر", personality="شاد", speaking_style="خودمانی")
        # A new persona still needs a fresh provider check for the new ticket.
        with patch.object(readiness.probe_ticket, "delay") as queued, self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(services.match_ticket(again))
        queued.assert_called_once()
        ticket.refresh_from_db()
        self.assertEqual(ticket.state, "MATCHED")

    def test_probe_failure_never_creates_chat_in_direct_or_fallback_mode(self):
        self.readiness_patch.stop()
        for direct in (True, False):
            cache.clear()
            ticket = (matchmaking.enqueue(self.human, self.mode.key, ai_consent=True)
                      if direct else self.fallback_ticket())
            if not direct:
                self.make_due(ticket)
            with patch.object(readiness.probe_ticket, "delay") as queued, self.captureOnCommitCallbacks(execute=True):
                self.assertFalse(services.match_ticket(ticket))
            with patch("apps.ai_players.client.generate", side_effect=client.ProviderError("network_error", True)):
                readiness.probe_ticket(*queued.call_args.args)
            self.assertFalse(services.match_ticket(ticket))
            ticket.refresh_from_db()
            self.assertEqual(ticket.state, "QUEUED")
            self.assertFalse(AIConversation.objects.exists())
            self.assertFalse(Message.objects.exists())
            matchmaking.cancel(self.human)

    def test_expired_or_changed_config_probe_cannot_allow_match(self):
        self.readiness_patch.stop()
        ticket = self.fallback_ticket()
        self.make_due(ticket)
        key = readiness.ticket_key(ticket.pk)
        cache.set(key, "ready", timeout=15)
        with override_settings(OPENAI_API_KEY="replacement-key"):
            self.assertFalse(services.match_ticket(ticket))
        cache.delete(key)
        self.assertFalse(services.match_ticket(ticket))
        self.assertFalse(AIConversation.objects.exists())

    def test_cancelled_ticket_does_not_probe_or_create_room(self):
        self.readiness_patch.stop()
        ticket = self.fallback_ticket()
        self.make_due(ticket)
        with patch.object(readiness.probe_ticket, "delay") as queued, self.captureOnCommitCallbacks(execute=True):
            services.match_ticket(ticket)
        matchmaking.cancel(self.human)
        with patch("apps.ai_players.client.generate") as generate:
            readiness.probe_ticket(*queued.call_args.args)
        generate.assert_not_called()
        self.assertFalse(services.match_ticket(ticket))
        self.assertFalse(AIConversation.objects.exists())

    def test_known_outage_blocks_previously_healthy_ticket(self):
        self.readiness_patch.stop()
        ticket = self.fallback_ticket()
        self.make_due(ticket)
        cache.set(readiness.ticket_key(ticket.pk), "ready", timeout=15)
        readiness.mark_unavailable("http_503")
        self.assertFalse(services.match_ticket(ticket))
        self.assertFalse(AIConversation.objects.exists())

    def test_existing_chat_failure_is_silent_and_room_stays_open(self):
        state = self.matched()
        with patch("apps.ai_players.client.generate", side_effect=client.ProviderError("http_401")):
            tasks.respond(str(state.pk))
        state.refresh_from_db()
        state.conversation.refresh_from_db()
        self.assertEqual(state.last_error, "http_401")
        self.assertEqual(AIRequest.objects.get().status, "FAILED")
        self.assertEqual(state.conversation.status, "ACTIVE")
        self.assertFalse(Message.objects.exists())

    def test_error_cleanup_only_removes_system_errors(self):
        state = self.matched()
        error = Message.objects.create(conversation_id=state.pk, type="SYSTEM", meta={"ai_error": "network_error"}, body="old error")
        normal = Message.objects.create(conversation_id=state.pk, sender=self.human, body="سلام")
        migration = import_module("apps.ai_players.migrations.0007_remove_chat_error_notices")
        migration.remove_errors(apps, SimpleNamespace(connection=connection))
        self.assertFalse(Message.objects.filter(pk=error.pk).exists())
        self.assertTrue(Message.objects.filter(pk=normal.pk).exists())
        state.conversation.refresh_from_db()
        self.assertEqual(state.conversation.last_message_preview, "سلام")

    def test_admin_can_create_edit_disable_persona(self):
        admin = User.objects.create_superuser(username="ai-admin", password="test-only")
        self.client.force_login(admin)
        data = {
            "first_name": "آوا", "last_name": "داستانی", "age": 26, "city": "تبریز",
            "gender": "F", "avatar": "a1", "bio": "شخصیت AI", "interests": "نقاشی",
            "personality": "صبور", "speaking_style": "خودمانی", "is_active": "on", "_save": "Save",
        }
        response = self.client.post("/admin/ai_players/persona/add/", data)
        self.assertEqual(response.status_code, 302)
        created = Persona.objects.get(first_name="آوا")
        self.assertFalse(created.user.has_usable_password())
        data.pop("is_active")
        data["city"] = "تهران"
        self.assertEqual(self.client.post(f"/admin/ai_players/persona/{created.pk}/change/", data).status_code, 302)
        created.refresh_from_db()
        self.assertFalse(created.is_active)
        self.assertEqual(created.city, "تهران")

    def test_responses_api_contract_and_failure_redaction(self):
        response = {"status": "completed", "output": [
            {"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": json.dumps(self.reply(None, None, "chat")[0])}]}],
            "usage": {"input_tokens": 12, "output_tokens": 4}}
        with patch("apps.ai_players.client.urlopen") as http:
            http.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            reply, usage = client.generate(self.persona, {"history": []}, "chat")
            request = http.call_args.args[0]
            body = json.loads(request.data)
            profile = json.loads(body["input"][0]["content"])["fictional_profile"]
            self.assertNotIn("disclosure", profile)
            self.assertEqual(profile["first_name"], self.persona.first_name)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
            self.assertIsNone(request.get_header("X-openai-actor-authorization"))
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
            self.assertEqual(body["text"]["format"]["schema"]["properties"]["choice"]["enum"], ["TRUTH"])
            self.assertEqual(reply["action"], "chat")
            self.assertEqual(usage["input_tokens"], 12)
            http.side_effect = HTTPError(request.full_url, 401, "SECRET", {}, None)
            with self.assertRaises(client.ProviderError) as failure:
                client.generate(self.persona, {}, "chat")
            self.assertEqual(str(failure.exception), "http_401")

    @override_settings(OPENAI_BASE_URL="https://provider.example/backend-api/codex/",
                       OPENAI_EXTRA_HEADERS={"x-openai-actor-authorization": "enabled"})
    def test_provider_url_and_headers_keep_responses_contract(self):
        response = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(self.reply(None, None, "chat")[0])}]}]}
        with patch("apps.ai_players.client.urlopen") as http:
            http.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            reply, _ = client.generate(self.persona, {"history": []}, "chat")
        request = http.call_args.args[0]
        self.assertEqual(request.full_url, "https://provider.example/backend-api/codex/responses")
        self.assertEqual(request.get_header("X-openai-actor-authorization"), "enabled")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
        body = json.loads(request.data)
        self.assertFalse(body["store"])
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(reply["action"], "chat")

    def test_provider_rejects_refusal_incomplete_and_invalid_actions(self):
        cases = [
            ({"status": "incomplete"}, "incomplete_response"),
            ({"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]}, "refusal"),
            ({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"action":"delete","text":"bad","choice":"TRUTH"}'}]}]}, "invalid_action"),
        ]
        with patch("apps.ai_players.client.urlopen") as http:
            for body, code in cases:
                http.return_value.__enter__.return_value.read.return_value = json.dumps(body).encode()
                with self.assertRaises(client.ProviderError) as failure:
                    client.generate(self.persona, {}, "chat")
                self.assertEqual(failure.exception.code, code)

    def fallback_ticket(self, consent=False):
        mode, _ = MatchMode.objects.get_or_create(key="quick", defaults={"title": "سریع"})
        return matchmaking.enqueue(self.human, mode.key, ai_consent=consent)

    def make_due(self, ticket):
        now = timezone.now()
        MatchTicket.objects.filter(pk=ticket.pk).update(
            created_at=now - timedelta(seconds=121), ai_fallback_at=now - timedelta(seconds=1))
        ticket.refresh_from_db()

    def test_fallback_threshold_is_two_minutes_and_persisted_on_reconnect(self):
        ticket = self.fallback_ticket()
        self.assertAlmostEqual((ticket.ai_fallback_at - ticket.created_at).total_seconds(), 120, delta=1)
        again = matchmaking.enqueue(self.human, ticket.mode.key, ai_consent=True)
        self.assertEqual(again.ai_fallback_at, ticket.ai_fallback_at)
        self.assertFalse(services.match_ticket(ticket))
        self.make_due(ticket)
        matchmaking._match_once()
        ticket.refresh_from_db()
        self.assertEqual(ticket.state, "MATCHED")
        self.assertTrue(AIConversation.objects.filter(pk=ticket.conversation_id).exists())

    def test_fallback_matches_at_two_minutes_but_not_before(self):
        now = timezone.now()
        with patch("django.utils.timezone.now", return_value=now):
            ticket = self.fallback_ticket()
        with patch("django.utils.timezone.now", return_value=now + timedelta(seconds=119)):
            matchmaking._match_once()
        ticket.refresh_from_db()
        self.assertEqual(ticket.state, "QUEUED")
        self.assertFalse(AIConversation.objects.exists())
        with patch("django.utils.timezone.now", return_value=now + timedelta(seconds=120)):
            matchmaking._match_once()
        ticket.refresh_from_db()
        self.assertEqual(ticket.state, "MATCHED")
        self.assertTrue(AIConversation.objects.filter(pk=ticket.conversation_id).exists())

    def test_fallback_is_automatic_without_consent_flag(self):
        self.fallback_ticket(consent=False)
        MatchTicket.objects.all().delete()
        response = self.client.post("/api/match/", {"mode": "quick"}, format="json")
        self.assertEqual(response.status_code, 201)
        ticket = MatchTicket.objects.get()
        self.assertFalse(ticket.ai_consent)
        self.assertIsNotNone(ticket.ai_fallback_at)
        self.make_due(ticket)
        self.assertTrue(services.match_ticket(ticket))
        with self.assertRaises(DomainError):
            matchmaking.enqueue(self.human, self.mode.key)

    def test_fallback_does_not_fill_groups_or_cancel_on_unavailable_provider(self):
        mode = MatchMode.objects.create(key="group", title="گروهی", size_min=3, size_max=5)
        group_ticket = matchmaking.enqueue(self.human, mode.key, ai_consent=True)
        self.assertIsNone(group_ticket.ai_fallback_at)
        self.make_due(group_ticket)
        self.assertFalse(services.match_ticket(group_ticket))
        matchmaking.cancel(self.human)
        ticket = self.fallback_ticket()
        self.make_due(ticket)
        with override_settings(AI_PLAYERS_ENABLED=False):
            matchmaking._match_once()
        ticket.refresh_from_db()
        self.assertEqual(ticket.state, "QUEUED")

    def test_human_match_takes_priority_over_due_ai_fallback(self):
        ticket = self.fallback_ticket()
        self.make_due(ticket)
        other = User.objects.create_user(username="partner", display_name="هم‌بازی", gender="F", birth_date=date(1998, 1, 1))
        other_ticket = matchmaking.enqueue(other, ticket.mode.key)
        matchmaking._match_once()
        ticket.refresh_from_db()
        other_ticket.refresh_from_db()
        self.assertEqual(ticket.state, "MATCHED")
        self.assertEqual(ticket.conversation_id, other_ticket.conversation_id)
        self.assertFalse(AIConversation.objects.exists())

    def test_cancelled_fallback_never_matches(self):
        ticket = self.fallback_ticket()
        self.make_due(ticket)
        matchmaking.cancel(self.human)
        self.assertFalse(services.match_ticket(ticket))
        self.assertFalse(AIConversation.objects.exists())

    def test_ai_always_chooses_truth_even_if_provider_sends_dare(self):
        state = self.matched()
        Prompt.objects.create(type="TRUTH", text="چه چیزی دوست داری؟", review_status="APPROVED", is_active=True)
        with patch("apps.game.services.random.shuffle", side_effect=lambda ids: ids.sort(reverse=True)):
            session = game.start_game(self.human, state.conversation)
        turn = game.current_turn(session)
        tasks._apply(state, {"action": "choose", "choice": "DARE"}, (turn.pk,), uuid.uuid4())
        turn.refresh_from_db()
        self.assertEqual(turn.prompt.type, "TRUTH")

    def test_ai_never_falls_back_to_dare_without_approved_truth(self):
        state = self.matched()
        Prompt.objects.create(type="DARE", text="بخند", review_status="APPROVED", is_active=True)
        with patch("apps.game.services.random.shuffle", side_effect=lambda ids: ids.sort(reverse=True)):
            session = game.start_game(self.human, state.conversation)
        turn = game.current_turn(session)
        with self.assertRaises(DomainError) as error:
            tasks._apply(state, {"action": "choose", "choice": "DARE"}, (turn.pk,), uuid.uuid4())
        self.assertEqual(error.exception.code, "no_prompts")
        turn.refresh_from_db()
        self.assertEqual(turn.status, TurnStatus.CHOOSING)

    def test_expiry_closes_once_ends_game_and_preserves_history_without_provider(self):
        state = self.matched()
        session = game.start_game(self.human, state.conversation)
        self.assertGreaterEqual((state.expires_at - state.started_at).total_seconds(), 599.5)
        self.assertLessEqual((state.expires_at - state.started_at).total_seconds(), 1200.5)
        self.assertFalse(services.expire_session(state.pk))
        AIConversation.objects.filter(pk=state.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with override_settings(AI_PLAYERS_ENABLED=False), self.captureOnCommitCallbacks(execute=True):
            tasks.recover_pending()
            tasks.recover_pending()
        state.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(state.conversation.status, "CLOSED")
        self.assertEqual(session.status, "ENDED")
        self.assertEqual(session.ended_reason, "ai_time_limit")
        self.assertEqual(Message.objects.filter(conversation_id=state.pk, meta__ai_session_ended=True).count(), 1)
        self.assertGreater(Message.objects.filter(conversation_id=state.pk).count(), 1)

    def test_expired_session_rejects_messages_and_turns_before_scheduler_runs(self):
        state = self.matched()
        session = game.start_game(self.human, state.conversation)
        AIConversation.objects.filter(pk=state.pk).update(expires_at=timezone.now())
        with self.assertRaises(DomainError) as error:
            chat.post_message(conversation=state.conversation, sender=self.human, body="سلام")
        self.assertEqual(error.exception.code, "ai_session_ended")
        with self.assertRaises(DomainError):
            game.choose(self.human, game.current_turn(session).pk, "TRUTH")

    def test_inflight_expiry_discards_reply(self):
        state = self.matched()
        def late(*args):
            AIConversation.objects.filter(pk=state.pk).update(expires_at=timezone.now())
            return self.reply(*args)
        with patch("apps.ai_players.client.generate", side_effect=late):
            tasks.respond(str(state.pk))
        self.assertFalse(Message.objects.filter(sender=self.persona.user).exists())
        self.assertEqual(AIRequest.objects.get().status, "STALE")

    def test_admin_switch_applies_to_waiting_tickets_and_preserves_active_sessions(self):
        config = AISettings.load()
        ticket = self.fallback_ticket()
        self.make_due(ticket)
        config.fallback_enabled = False
        config.save()
        self.assertFalse(services.match_ticket(ticket))
        self.assertIsNone(matchmaking.status(self.human)["ai_fallback_at"])
        config.fallback_enabled = True
        config.save()
        self.assertTrue(services.match_ticket(ticket))
        ticket.refresh_from_db()
        state = AIConversation.objects.get(pk=ticket.conversation_id)
        config.fallback_enabled = False
        config.save()
        self.assertTrue(services.valid(state))

    def test_duration_uses_database_range_and_existing_session_deadline_is_fixed(self):
        config = AISettings.load()
        self.assertEqual((config.session_min_minutes, config.session_max_minutes), (10, 20))
        config.session_min_minutes, config.session_max_minutes = 12, 18
        config.save()
        with patch("apps.ai_players.models.random.randint", return_value=900) as random_duration:
            state = self.matched()
        random_duration.assert_called_once_with(720, 1080)
        self.assertAlmostEqual((state.expires_at - state.started_at).total_seconds(), 900, delta=1)
        deadline = state.expires_at
        config.session_min_minutes = config.session_max_minutes = 2
        config.save()
        state.refresh_from_db()
        self.assertEqual(state.expires_at, deadline)
        chat.close_room(self.human, state.conversation)
        Persona.objects.create(first_name="تازه", last_name="نمونه", age=25, city="شیراز",
            bio="شخصیت داستانی", interests="هنر", personality="شاد", speaking_style="خودمانی")
        replacement = self.matched()
        self.assertNotEqual(replacement.persona_id, state.persona_id)
        self.assertAlmostEqual((replacement.expires_at - replacement.started_at).total_seconds(), 120, delta=1)

    def test_settings_admin_validates_range_and_public_api_updates(self):
        config = AISettings.load()
        config.session_min_minutes = 21
        with self.assertRaises(ValidationError):
            config.full_clean()
        admin = User.objects.create_superuser(username="settings-admin", password="test-only")
        self.client.force_login(admin)
        url = "/admin/ai_players/aisettings/1/change/"
        response = self.client.post(url, {"session_min_minutes": 21, "session_max_minutes": 20, "_save": "Save"})
        self.assertEqual(response.status_code, 200)
        config.refresh_from_db()
        self.assertEqual(config.session_min_minutes, 10)
        self.assertEqual(self.client.post(url, {"session_min_minutes": 7, "session_max_minutes": 13, "_save": "Save"}).status_code, 302)
        config.refresh_from_db()
        self.assertFalse(config.fallback_enabled)
        self.assertEqual(self.client.get("/api/lobby/").data["ai_settings"], config.public_payload())
        self.assertEqual(self.client.get("/api/ai/personas/").data["settings"], config.public_payload())
