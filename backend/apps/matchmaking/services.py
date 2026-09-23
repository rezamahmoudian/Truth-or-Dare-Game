"""Matchmaking.

Matching runs in one place — a Celery task guarded by a Redis lock — rather
than in each client or in parallel workers. Two users independently concluding
they matched each other produces split rooms, which is miserable to reproduce
and trivial to prevent by serialising the decision.
"""

import logging
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from apps.chat import broadcast
from apps.chat import services as chat_services
from apps.chat.models import (
    Conversation,
    ConversationStatus,
    ConversationType,
    Participant,
)
from apps.core.errors import DomainError
from apps.matchmaking.lock import redis_lock
from apps.matchmaking.models import MatchMode, MatchTicket, TicketState
from apps.matchmaking.payloads import ticket_payload
from apps.users.models import Block, User

logger = logging.getLogger("ft.match")

LOCK_KEY = "mm:lock"


# ---------------------------------------------------------------------------
# Queue membership
# ---------------------------------------------------------------------------


def active_ticket(user: User) -> MatchTicket | None:
    return (
        MatchTicket.objects.filter(user=user, state=TicketState.QUEUED)
        .select_related("mode")
        .first()
    )


def used_today(user: User, mode: MatchMode) -> int:
    since = timezone.now() - timedelta(hours=24)
    return MatchTicket.objects.filter(
        user=user, mode=mode, created_at__gte=since
    ).count()


def remaining_today(user: User, mode: MatchMode) -> int | None:
    if not mode.daily_limit:
        return None
    return max(0, mode.daily_limit - used_today(user, mode))


def enqueue(user: User, mode_key: str) -> MatchTicket:
    mode = MatchMode.objects.filter(key=mode_key, is_active=True).first()
    if mode is None:
        raise DomainError("mode_not_found", "این حالت بازی موجود نیست.", 404)

    if not user.is_onboarded:
        raise DomainError("profile_incomplete", "اول پروفایلت رو کامل کن.", 409)
    if user.age is not None and user.age < mode.min_age:
        raise DomainError("too_young", "این حالت برای سن شما نیست.", 403)

    remaining = remaining_today(user, mode)
    if remaining == 0:
        raise DomainError(
            "daily_limit", "سهمیه امروز این حالت تمام شده است.", 429
        )

    existing = active_ticket(user)
    if existing:
        # Re-enqueueing the same mode is what a reconnecting client does; it is
        # not an error, and minting a second ticket would put them in the queue
        # twice.
        if existing.mode_id == mode.pk:
            return existing
        cancel(user, notify=False)

    try:
        ticket = MatchTicket.objects.create(
            user=user,
            mode=mode,
            my_gender=user.gender,
            want_gender=mode.target_gender,
            size_min=mode.size_min,
            size_max=mode.size_max,
            category=mode.category,
        )
    except IntegrityError:
        # Two enqueues raced; the other one won.
        found = active_ticket(user)
        if found is None:
            raise
        return found

    logger.info(
        "mm.enqueue",
        extra={"event": "mm.enqueue", "user_id": user.pk, "mode": mode.key},
    )
    _notify(ticket, "mm.queued")
    return ticket


def cancel(user: User, *, notify: bool = True) -> None:
    ticket = active_ticket(user)
    if ticket is None:
        return
    ticket.state = TicketState.CANCELLED
    ticket.save(update_fields=["state"])
    logger.info("mm.cancel", extra={"event": "mm.cancel", "user_id": user.pk})
    if notify:
        _notify(ticket, "mm.cancelled")


def status(user: User) -> dict | None:
    ticket = active_ticket(user)
    if ticket is None:
        return None
    return ticket_payload(
        ticket,
        waited=_waited(ticket),
        queue_size=_queue_size(ticket),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _waited(ticket: MatchTicket) -> int:
    return int((timezone.now() - ticket.created_at).total_seconds())


def _queue_size(ticket: MatchTicket) -> int:
    """How many people are waiting for a room of the same shape.

    Shown to the user because a silent waiting screen reads as broken; a number
    that moves reads as a queue.
    """
    return MatchTicket.objects.filter(
        state=TicketState.QUEUED,
        size_min=ticket.size_min,
        size_max=ticket.size_max,
    ).count()


def queue_sizes() -> dict[tuple[int, int], int]:
    """How many people are waiting, grouped by the shape of room they want."""
    rows = (
        MatchTicket.objects.filter(state=TicketState.QUEUED)
        .values("size_min", "size_max")
        .annotate(total=Count("id"))
    )
    return {(row["size_min"], row["size_max"]): row["total"] for row in rows}


def recently_active(limit: int = 12) -> list[User]:
    """People seen in the last few minutes, for the lobby's presence row.

    Guests without a finished profile are skipped — a row of blank avatars
    makes the app look emptier than it is, not fuller.
    """
    cutoff = timezone.now() - timedelta(minutes=settings.LOBBY_ACTIVE_MINUTES)
    return list(
        User.objects.filter(is_active=True, last_seen_at__gte=cutoff)
        .exclude(display_name="")
        .order_by("-last_seen_at")[:limit]
    )


def online_count() -> int:
    cutoff = timezone.now() - timedelta(minutes=settings.LOBBY_ACTIVE_MINUTES)
    return User.objects.filter(is_active=True, last_seen_at__gte=cutoff).count()


def _notify(ticket: MatchTicket, event: str, extra: dict | None = None) -> None:
    payload = ticket_payload(
        ticket, waited=_waited(ticket), queue_size=_queue_size(ticket)
    )
    payload.update(extra or {})
    broadcast.to_users([ticket.user_id], event, payload)


def _effective_want_gender(ticket: MatchTicket) -> str:
    return "" if ticket.widened else ticket.want_gender


def _effective_category(ticket: MatchTicket) -> str:
    return "" if ticket.widened else ticket.category


def _compatible(a: MatchTicket, b: MatchTicket) -> bool:
    if (a.size_min, a.size_max) != (b.size_min, b.size_max):
        return False

    cat_a, cat_b = _effective_category(a), _effective_category(b)
    if cat_a and cat_b and cat_a != cat_b:
        return False

    # Each side's filter has to be satisfied by the other. "Play with a girl"
    # and "play with a boy" are the same match seen from two directions, which
    # is why gender lives on the ticket rather than the queue.
    want_a, want_b = _effective_want_gender(a), _effective_want_gender(b)
    wants_met = (not want_a or want_a == b.my_gender) and (
        not want_b or want_b == a.my_gender
    )
    return wants_met


def _blocked_pairs(user_ids: list[int]) -> set[tuple[int, int]]:
    pairs = set()
    for blocker, blocked in Block.objects.filter(
        blocker_id__in=user_ids, blocked_id__in=user_ids
    ).values_list("blocker_id", "blocked_id"):
        pairs.add((blocker, blocked))
        pairs.add((blocked, blocker))
    return pairs


def _recent_partners(user_ids: list[int]) -> dict[int, set[int]]:
    """Who each user has just played with.

    Being handed the same stranger twice in a row makes the pool feel tiny even
    when it is not, so recent partners are skipped while anyone else is
    available.
    """
    cutoff = timezone.now() - timedelta(
        minutes=settings.MATCH_RECENT_PARTNER_MINUTES
    )
    conversation_ids = Participant.objects.filter(
        user_id__in=user_ids, conversation__created_at__gte=cutoff
    ).values_list("conversation_id", flat=True)

    members = defaultdict(set)
    for conversation_id, user_id in Participant.objects.filter(
        conversation_id__in=list(conversation_ids)
    ).values_list("conversation_id", "user_id"):
        members[conversation_id].add(user_id)

    partners: dict[int, set[int]] = defaultdict(set)
    for group in members.values():
        for user_id in group:
            partners[user_id] |= group - {user_id}
    return partners


# ---------------------------------------------------------------------------
# The matcher
# ---------------------------------------------------------------------------


def run_matcher() -> dict:
    """One pass over the queue. Returns a small summary for logging."""
    with redis_lock(LOCK_KEY) as acquired:
        if not acquired:
            return {"skipped": "locked"}
        return _match_once()


def _match_once() -> dict:
    tickets = list(
        MatchTicket.objects.filter(state=TicketState.QUEUED)
        .select_related("mode", "user")
        .order_by("created_at")
    )
    if not tickets:
        return {"queued": 0}

    expired = _expire_stale(tickets)
    tickets = [t for t in tickets if t.state == TicketState.QUEUED]

    widened = _widen_overdue(tickets)

    groups = _form_groups(tickets)
    for group in groups:
        _commit_group(group)

    # Everyone still waiting gets a heartbeat so the screen keeps moving.
    matched_ids = {t.pk for group in groups for t in group}
    for ticket in tickets:
        if ticket.pk not in matched_ids:
            _notify(ticket, "mm.searching")

    return {
        "queued": len(tickets),
        "matched": len(matched_ids),
        "groups": len(groups),
        "widened": widened,
        "expired": expired,
    }


def _expire_stale(tickets: list[MatchTicket]) -> int:
    limit = settings.MATCH_TICKET_TTL_SECONDS
    count = 0
    for ticket in tickets:
        if _waited(ticket) < limit:
            continue
        ticket.state = TicketState.EXPIRED
        ticket.save(update_fields=["state"])
        # Naming a concrete alternative beats an apology: the group queue is
        # the one that always fills.
        _notify(ticket, "mm.expired", {"suggested_mode": "group"})
        count += 1
    return count


def _widen_overdue(tickets: list[MatchTicket]) -> int:
    count = 0
    for ticket in tickets:
        if ticket.widened or _waited(ticket) < ticket.mode.widen_after_seconds:
            continue
        ticket.widened = True
        ticket.save(update_fields=["widened"])
        logger.info(
            "mm.widened",
            extra={"event": "mm.widened", "user_id": ticket.user_id},
        )
        count += 1
    return count


def _prioritise(tickets: list[MatchTicket]) -> list[MatchTicket]:
    """Oldest first, except the scarce side of the queue goes ahead.

    Gender-filtered modes are asymmetric in practice: one direction has far
    more demand than supply. Serving the under-supplied side first shortens the
    wait for the people whose presence makes those queues work at all.
    """
    counts = Counter(t.my_gender for t in tickets if t.my_gender)
    minority = min(counts, key=lambda g: counts[g]) if len(counts) > 1 else None
    return sorted(
        tickets,
        key=lambda t: (0 if minority and t.my_gender == minority else 1, t.created_at),
    )


def _form_groups(tickets: list[MatchTicket]) -> list[list[MatchTicket]]:
    if not tickets:
        return []

    user_ids = [t.user_id for t in tickets]
    blocked = _blocked_pairs(user_ids)
    recent = _recent_partners(user_ids)

    def allowed(a: MatchTicket, b: MatchTicket) -> bool:
        if (a.user_id, b.user_id) in blocked:
            return False
        # A recent partner is only refused while the ticket still has its
        # original constraints; once widened, playing again beats not playing.
        if not (a.widened or b.widened) and b.user_id in recent.get(a.user_id, ()):
            return False
        return _compatible(a, b)

    ordered = _prioritise(tickets)
    used: set[int] = set()
    groups: list[list[MatchTicket]] = []

    for index, seed in enumerate(ordered):
        if seed.pk in used:
            continue

        group = [seed]
        for candidate in ordered[index + 1 :]:
            if candidate.pk in used or len(group) >= seed.size_max:
                continue
            if all(allowed(member, candidate) for member in group):
                group.append(candidate)

        full = len(group) >= seed.size_max
        # A group mode fills to its maximum when it can, but once the oldest
        # ticket has been relaxed, starting with the minimum beats waiting for
        # people who are not there.
        enough = len(group) >= seed.size_min and any(t.widened for t in group)

        if full or enough:
            used.update(t.pk for t in group)
            groups.append(group)

    return groups


@transaction.atomic
def _commit_group(group: list[MatchTicket]) -> Conversation:
    mode = group[0].mode

    conversation = Conversation.objects.create(
        type=ConversationType.ROOM,
        status=ConversationStatus.ACTIVE,
        code=Conversation.generate_code(),
        max_players=mode.size_max,
        # The longest-waiting player owns the room, so a matched room has a
        # close button belonging to someone from the moment it exists.
        # (group[0] is the seed of the grouping pass, which priority ordering
        # may have put first for being the scarce side — not for waiting
        # longest.)
        owner_id=min(group, key=lambda t: t.created_at).user_id,
    )
    Participant.objects.bulk_create(
        Participant(conversation=conversation, user_id=t.user_id) for t in group
    )

    MatchTicket.objects.filter(pk__in=[t.pk for t in group]).update(
        state=TicketState.MATCHED, conversation=conversation
    )

    names = "، ".join(t.user.display_name or t.user.username for t in group)
    chat_services.post_system_message(
        conversation,
        f"{names} به هم وصل شدند. اول سلام کنید — هر وقت آماده بودید بازی را شروع کنید.",
    )

    logger.info(
        "mm.matched",
        extra={
            "event": "mm.matched",
            "conversation_id": str(conversation.id),
            "mode": mode.key,
            "players": len(group),
        },
    )

    payload = {
        "conversation_id": str(conversation.id),
        "mode": mode.key,
        "player_ids": [t.user_id for t in group],
    }
    transaction.on_commit(
        lambda: broadcast.to_users([t.user_id for t in group], "mm.matched", payload)
    )
    return conversation
