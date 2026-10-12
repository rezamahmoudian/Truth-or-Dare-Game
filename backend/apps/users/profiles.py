"""Public profile details and achievements derived from recorded play."""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.game.models import GameSession, Turn
from apps.users.payloads import person_payload


def profile_payload(user, *, relation):
    result = person_payload(user, relation=relation)
    totals = Turn.objects.filter(player=user, status="DONE", answer_message__isnull=False).aggregate(
        truths=Count("pk", filter=Q(choice="TRUTH")),
        dares=Count("pk", filter=Q(choice="DARE")),
    )
    games = GameSession.objects.filter(Q(turn_order__contains=[user.pk]) | Q(turns__player=user)).distinct().count()
    streak = user.streak_days if user.last_played_on and user.last_played_on >= timezone.localdate() - timedelta(days=1) else 0
    result["joined_at"] = user.date_joined.date().isoformat()
    result["stats"] = {"games": games, **totals, "streak_days": streak}
    milestones = [
        ("first_game", "قدم اول", "شرکت در اولین بازی", "🎲", games, 1),
        ("regular", "پایهٔ بازی", "شرکت در ۱۰ بازی", "⭐", games, 10),
        ("veteran", "هم‌بازی حرفه‌ای", "شرکت در ۵۰ بازی", "🏆", games, 50),
        ("truth", "راست‌گو", "انجام ۱۰ نوبت حقیقت", "💬", totals["truths"], 10),
        ("dare", "دل‌وجرئت", "انجام ۱۰ نوبت جرئت", "🔥", totals["dares"], 10),
    ]
    result["badges"] = [dict(key=key, title=title, description=description, icon=icon,
        earned=value >= target, progress=min(value, target), target=target)
        for key, title, description, icon, value, target in milestones]
    return result
