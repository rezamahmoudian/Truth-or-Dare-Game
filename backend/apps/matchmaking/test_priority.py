from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.chat.models import Conversation, Participant
from apps.matchmaking import services
from apps.matchmaking.models import MatchMode, MatchTicket
from apps.users.models import Block, User


@override_settings(AI_PLAYERS_ENABLED=False)
class GenderQueuePriorityTests(TestCase):
    def setUp(self):
        self.quick = MatchMode.objects.create(key="quick-test", title="شروع سریع")
        self.girls = MatchMode.objects.create(key="girls-test", title="بازی با دختر", target_gender="F")
        self.boys = MatchMode.objects.create(key="boys-test", title="بازی با پسر", target_gender="M")
        self.broadcast = patch("apps.chat.broadcast.to_users").start()
        self.addCleanup(patch.stopall)

    def ticket(self, gender, mode, seconds=0, widened=False, **overrides):
        user = User.objects.create_user(
            username=f"priority-{User.objects.count()}", display_name="بازیکن",
            gender=gender, birth_date=date(1995, 1, 1),
        )
        ticket = MatchTicket.objects.create(
            user=user, mode=mode, my_gender=gender, want_gender=mode.target_gender,
            size_min=mode.size_min, size_max=mode.size_max, widened=widened, **overrides,
        )
        MatchTicket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(seconds=seconds))
        ticket.refresh_from_db()
        return ticket

    def matched_together(self, first, second):
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.state, "MATCHED")
        self.assertEqual(first.conversation_id, second.conversation_id)
        self.assertEqual(set(Participant.objects.filter(conversation_id=first.conversation_id)
                             .values_list("user_id", flat=True)), {first.user_id, second.user_id})

    def test_girl_in_quick_goes_to_gender_queue_before_older_quick_waiter(self):
        quick = self.ticket("M", self.quick, seconds=15)
        filtered = self.ticket("M", self.girls, seconds=10)
        girl = self.ticket("F", self.quick)
        result = services._match_once()
        self.matched_together(filtered, girl)
        quick.refresh_from_db()
        self.assertEqual(quick.state, "QUEUED")
        self.assertEqual(result["groups"], 1)

    def test_oldest_gender_request_wins_even_after_widening(self):
        quick = self.ticket("M", self.quick, seconds=70)
        oldest = self.ticket("M", self.girls, seconds=60)
        newer = self.ticket("M", self.girls, seconds=10)
        girl = self.ticket("F", self.quick)
        services._match_once()
        self.matched_together(oldest, girl)
        oldest.refresh_from_db()
        self.assertTrue(oldest.widened)
        self.assertNotEqual(newer.conversation_id, girl.conversation_id)
        self.assertNotEqual(quick.conversation_id, girl.conversation_id)

    def test_quick_matches_normally_without_gender_request(self):
        quick = self.ticket("M", self.quick, seconds=5)
        girl = self.ticket("F", self.quick)
        services._match_once()
        self.matched_together(quick, girl)

    def test_blocked_filtered_waiter_does_not_hold_up_quick_pair(self):
        quick = self.ticket("M", self.quick, seconds=15)
        filtered = self.ticket("M", self.girls, seconds=10)
        girl = self.ticket("F", self.quick)
        Block.objects.create(blocker=girl.user, blocked=filtered.user)
        services._match_once()
        self.matched_together(quick, girl)
        filtered.refresh_from_db()
        self.assertEqual(filtered.state, "QUEUED")

    def test_boy_queue_has_same_priority_and_both_filters_are_respected(self):
        quick = self.ticket("F", self.quick, seconds=15)
        filtered = self.ticket("F", self.boys, seconds=10)
        boy = self.ticket("M", self.girls)
        services._match_once()
        self.matched_together(filtered, boy)
        quick.refresh_from_db()
        self.assertEqual(quick.state, "QUEUED")

    def test_recent_or_incompatible_filtered_waiter_cannot_take_quick_arrival(self):
        for reason in ("recent", "category", "other_filter"):
            with self.subTest(reason=reason):
                quick = self.ticket("M", self.quick, seconds=15)
                filtered = self.ticket("M", self.girls, seconds=10, category="DEEP")
                girl = self.ticket("F", self.quick, category="DEEP")
                if reason == "recent":
                    room = Conversation.objects.create(type="ROOM")
                    Participant.objects.bulk_create([
                        Participant(conversation=room, user=filtered.user),
                        Participant(conversation=room, user=girl.user),
                    ])
                elif reason == "category":
                    MatchTicket.objects.filter(pk=girl.pk).update(category="BOLD")
                else:
                    # She is explicitly seeking a girl, so neither man can meet her filter.
                    MatchTicket.objects.filter(pk=girl.pk).update(want_gender="F")
                services._match_once()
                if reason == "other_filter":
                    girl.refresh_from_db()
                    self.assertEqual(girl.state, "QUEUED")
                else:
                    self.matched_together(quick, girl)
                MatchTicket.objects.filter(state="QUEUED").update(state="CANCELLED")

    def test_leftover_girls_still_match_quick_after_gender_queue_is_served(self):
        quick = self.ticket("M", self.quick, seconds=15)
        filtered = self.ticket("M", self.girls, seconds=10)
        girl1 = self.ticket("F", self.quick, seconds=2)
        girl2 = self.ticket("F", self.quick)
        services._match_once()
        self.matched_together(filtered, girl1)
        self.matched_together(quick, girl2)
        self.assertNotEqual(girl1.conversation_id, girl2.conversation_id)

    def test_gender_request_in_group_mode_does_not_take_two_player_arrival(self):
        group = MatchMode.objects.create(key="group-girls", title="گروهی", target_gender="F", size_min=3, size_max=4)
        filtered = self.ticket("M", group)
        quick = self.ticket("M", self.quick, seconds=5)
        girl = self.ticket("F", self.quick)
        services._match_once()
        self.matched_together(quick, girl)
        filtered.refresh_from_db()
        self.assertEqual(filtered.state, "QUEUED")
