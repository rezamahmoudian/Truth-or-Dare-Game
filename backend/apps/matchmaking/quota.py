"""Count sustained, reciprocal chats, never attempts to find a partner."""

from datetime import timedelta

from django.utils import timezone

from apps.chat.models import Message, MessageType, Participant
from apps.matchmaking.models import MatchTicket, TicketState


GRACE_SECONDS = 60
CHAT_TYPES = (MessageType.TEXT, MessageType.GAME_ANSWER, MessageType.ATTACHMENT)


def pending(conversation_id):
    return MatchTicket.objects.filter(
        conversation_id=conversation_id, state=TicketState.MATCHED,
        matched_at__isnull=False, quota_consumed_at__isnull=True,
        quota_closed_at__isnull=True,
    )


def close_pending(conversation_id):
    """Caller holds the conversation lock; reopening must not revive a free exit."""
    pending(conversation_id).update(quota_closed_at=timezone.now())


def record_message(message):
    """Called atomically under the conversation lock after a successful send.

    Both sides must still participate after the first minute. Greetings followed
    by an immediate exit (including closing the browser) never qualify. Explicit
    departures seal pending tickets, so later friend chats cannot charge them.
    """
    if not message.sender_id or message.type not in CHAT_TYPES:
        return
    tickets = list(pending(message.conversation_id).filter(
        matched_at__lte=message.created_at - timedelta(seconds=GRACE_SECONDS),
    ))
    if not tickets:
        return
    active_ids = set(Participant.objects.filter(
        conversation_id=message.conversation_id, left_at__isnull=True,
    ).values_list("user_id", flat=True))
    for ticket in tickets:
        cutoff = ticket.matched_at + timedelta(seconds=GRACE_SECONDS)
        speakers = set(Message.objects.filter(
            conversation_id=message.conversation_id, created_at__gte=cutoff,
            sender_id__in=active_ids, type__in=CHAT_TYPES, is_deleted=False,
        ).order_by().values_list("sender_id", flat=True).distinct())
        if ticket.user_id in speakers and len(speakers) >= 2:
            pending(message.conversation_id).filter(pk=ticket.pk).update(
                quota_consumed_at=message.created_at,
            )
