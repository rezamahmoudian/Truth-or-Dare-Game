from apps.matchmaking.models import MatchMode, MatchTicket


def queue_state(queue_size: int, size_min: int) -> str:
    """How the queue looks right now, for the dot next to a mode.

    Derived from the real queue rather than decorative: someone deciding
    between two modes is choosing on this, and a green dot on an empty queue is
    a lie they find out about thirty seconds later.
    """
    if queue_size >= size_min:
        return "FAST"
    if queue_size > 0:
        return "SLOW"
    return "EMPTY"


def mode_payload(
    mode: MatchMode,
    *,
    remaining: int | None = None,
    queue_size: int = 0,
) -> dict:
    return {
        "key": mode.key,
        "title": mode.title,
        "subtitle": mode.subtitle,
        "emoji": mode.emoji,
        "accent": mode.accent,
        "size_min": mode.size_min,
        "size_max": mode.size_max,
        "target_gender": mode.target_gender,
        "is_featured": mode.is_featured,
        "daily_limit": mode.daily_limit,
        # None means unlimited; 0 means the cap is used up for today.
        "remaining_today": remaining,
        "queue_size": queue_size,
        "queue_state": queue_state(queue_size, mode.size_min),
    }


def ticket_payload(ticket: MatchTicket, *, waited: int = 0, queue_size: int = 0) -> dict:
    return {
        "id": ticket.pk,
        "mode": ticket.mode.key,
        "state": ticket.state,
        "widened": ticket.widened,
        "waited_seconds": waited,
        "queue_size": queue_size,
        "conversation_id": str(ticket.conversation_id) if ticket.conversation_id else None,
    }
