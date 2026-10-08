from datetime import date, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.chat.models import Conversation
from apps.matchmaking import services as matchmaking
from apps.matchmaking.models import MatchMode
from apps.users.models import User
from . import services
from .models import AIConversation, AIEncounter, Persona


@override_settings(AI_PLAYERS_ENABLED=True, OPENAI_API_KEY="test-only",
                   AI_DAILY_REQUEST_LIMIT=100, AI_USER_DAILY_REQUEST_LIMIT=100)
class LifetimeEncounterTests(TestCase):
    def setUp(self):
        self.human = User.objects.create_user(
            username="encounter-player", display_name="بازیکن", gender="M", birth_date=date(1995, 1, 1),
        )
        self.mode = MatchMode.objects.create(key="encounter-human", title="بازی دونفره")
        self.probe = patch("apps.ai_players.readiness.ready_for_ticket", return_value=True).start()
        self.addCleanup(patch.stopall)
        patch("apps.ai_players.services.notify").start()
        patch("apps.chat.broadcast.to_users").start()

    def persona(self, name):
        return Persona.objects.create(first_name=name, last_name="نمونه", age=24, city="شیراز",
                                      bio="شخصیت داستانی", interests="هنر", personality="شاد", speaking_style="خودمانی")

    def ticket(self, user=None):
        ticket = matchmaking.enqueue(user or self.human, self.mode.key)
        ticket.ai_fallback_at = timezone.now() - timedelta(seconds=1)
        ticket.save(update_fields=["ai_fallback_at"])
        return ticket

    def test_each_persona_once_then_only_new_persona_unlocks_matching(self):
        personas = [self.persona(name) for name in ("اول", "دوم", "سوم")]
        seen = set()
        for _ in personas:
            ticket = self.ticket()
            self.assertTrue(services.match_ticket(ticket))
            self.assertFalse(services.match_ticket(ticket))
            ticket.refresh_from_db()
            state = AIConversation.objects.get(pk=ticket.conversation_id)
            self.assertNotIn(state.persona_id, seen)
            seen.add(state.persona_id)
        self.assertEqual(seen, {p.pk for p in personas})
        ticket = self.ticket()
        self.probe.reset_mock()
        for _ in range(2):
            self.assertFalse(services.match_ticket(ticket))
        self.probe.assert_not_called()
        ticket.refresh_from_db()
        self.assertEqual(ticket.state, "QUEUED")
        self.assertIsNone(ticket.conversation_id)
        self.assertEqual(AIConversation.objects.count(), 3)
        new = self.persona("تازه")
        self.assertTrue(services.match_ticket(ticket))
        ticket.refresh_from_db()
        self.assertEqual(AIConversation.objects.get(pk=ticket.conversation_id).persona_id, new.pk)

    def test_expiry_profile_edit_reactivation_and_chat_deletion_do_not_reset_history(self):
        persona = self.persona("اول")
        ticket = self.ticket()
        self.assertTrue(services.match_ticket(ticket))
        ticket.refresh_from_db()
        AIConversation.objects.filter(pk=ticket.conversation_id).update(expires_at=timezone.now()-timedelta(days=90))
        Conversation.objects.filter(pk=ticket.conversation_id).update(status="CLOSED")
        persona.is_active = False
        persona.save()
        persona.first_name = "اسم تازه"
        persona.is_active = True
        persona.save()
        Conversation.objects.get(pk=ticket.conversation_id).delete()
        self.assertTrue(AIEncounter.objects.filter(human=self.human, persona=persona).exists())
        self.assertFalse(services.match_ticket(self.ticket()))
        other = User.objects.create_user(username="other-player", display_name="دیگری", gender="M", birth_date=date(1994, 1, 1))
        self.assertTrue(services.match_ticket(self.ticket(other)))

    def test_not_ready_and_rolled_back_match_do_not_consume_persona(self):
        persona = self.persona("اول")
        ticket = self.ticket()
        self.probe.return_value = False
        self.assertFalse(services.match_ticket(ticket))
        self.assertFalse(AIEncounter.objects.exists())
        self.probe.return_value = True
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.assertTrue(services.match_ticket(ticket))
                raise RuntimeError("rollback")
        self.assertFalse(AIEncounter.objects.exists())
        self.assertTrue(services.eligible_personas(self.human).filter(pk=persona.pk).exists())

    def test_migration_backfills_old_duplicate_sessions_once_with_earliest_date(self):
        persona = self.persona("اول")
        oldest = timezone.now() - timedelta(days=200)
        for started in (timezone.now(), oldest):
            room = Conversation.objects.create(type="ROOM")
            AIConversation.objects.create(conversation=room, human=self.human, persona=persona, started_at=started)
        AIEncounter.objects.all().delete()
        migration = import_module("apps.ai_players.migrations.0008_lifetime_encounters")
        for _ in range(2):
            migration.backfill_encounters(apps, SimpleNamespace(connection=connection))
        self.assertEqual(AIEncounter.objects.count(), 1)
        self.assertEqual(AIEncounter.objects.get().first_matched_at, oldest)
        self.assertFalse(services.eligible_personas(self.human).exists())
