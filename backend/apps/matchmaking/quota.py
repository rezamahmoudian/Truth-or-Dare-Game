"""Count sustained, reciprocal chats, never attempts to find a partner."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.chat.models import Conversation, Message, MessageType, Participant
from apps.matchmaking.models import MatchTicket, TicketState


GRACE_SECONDS = 60
CHAT_TYPES = (MessageType.TEXT, MessageType.GAME_ANSWER, MessageType.ATTACHMENT)


def pending(conversation_id):
    return MatchTicket.objects.filter(
        conversation_id=conversation_id, state=TicketState.MATCHED,
        matched_at__isnull=False, quota_consumed_at__isnull=True,
        quota_closed_at__isnull=True,
    )


def close_pending(conversation_id, *, expired_only=False):
    """Caller holds the conversation lock; reopening must not revive a free exit."""
    from apps.billing.wallets import locked_wallet, release_credit
    rows = pending(conversation_id)
    if expired_only:
        rows = rows.filter(funding_expires_at__lte=timezone.now())
    tickets = list(rows.select_related("user").order_by("user_id", "pk"))
    for user_id in sorted({t.user_id for t in tickets if t.uses_credit}):
        locked_wallet(user_id)
    for ticket in tickets:
        if ticket.uses_credit:
            release_credit(user=ticket.user, ticket_id=ticket.pk,
                           reason="پایان مهلت تعامل" if expired_only else "پایان مچ پیش از تعامل دوطرفه")
    rows.update(quota_closed_at=timezone.now())


def expire_pending():
    """Run by the existing matcher tick, even when the queue is empty."""
    ids = MatchTicket.objects.filter(state=TicketState.MATCHED,
        quota_closed_at__isnull=True, quota_consumed_at__isnull=True,
        funding_expires_at__lte=timezone.now()).values_list("conversation_id", flat=True).distinct()
    for conversation_id in list(ids):
        with transaction.atomic():
            if Conversation.objects.select_for_update().filter(pk=conversation_id).exists():
                close_pending(conversation_id, expired_only=True)


def record_message(message):
    """Called atomically under the conversation lock after a successful send.

    Both sides must still participate after the first minute. Greetings followed
    by an immediate exit (including closing the browser) never qualify. Explicit
    departures seal pending tickets, so later friend chats cannot charge them.
    """
    if not message.sender_id or message.type not in CHAT_TYPES:
        return
    from apps.billing.wallets import locked_wallet, consume_credit, release_credit
    for user_id in sorted(set(pending(message.conversation_id).filter(uses_credit=True).values_list("user_id", flat=True))):
        locked_wallet(user_id)
    close_pending(message.conversation_id, expired_only=True)
    tickets = list(pending(message.conversation_id).filter(
        matched_at__lte=message.created_at - timedelta(seconds=GRACE_SECONDS),
    ))
    if not tickets:
        return
    active_ids = set(Participant.objects.filter(
        conversation_id=message.conversation_id, left_at__isnull=True,
    ).values_list("user_id", flat=True))
    from apps.billing.models import ReservationStatus
    has_ai = Participant.objects.filter(conversation_id=message.conversation_id, user__is_ai=True).exists()
    for ticket in tickets:
        cutoff = ticket.matched_at + timedelta(seconds=GRACE_SECONDS)
        speakers = set(Message.objects.filter(
            conversation_id=message.conversation_id, created_at__gte=cutoff,
            sender_id__in=active_ids, type__in=CHAT_TYPES, is_deleted=False,
        ).order_by().values_list("sender_id", flat=True).distinct())
        if ticket.user_id in speakers and len(speakers) >= 2:
            if ticket.uses_credit and has_ai:
                release_credit(user=ticket.user, ticket_id=ticket.pk, reason="عدم تطابق مچ انسانی")
                pending(message.conversation_id).filter(pk=ticket.pk).update(quota_closed_at=timezone.now())
                continue
            pending(message.conversation_id).filter(pk=ticket.pk).update(
                quota_consumed_at=message.created_at,
            )
            if ticket.uses_credit:
                result = consume_credit(user=ticket.user, ticket_id=ticket.pk)
                if result.status != ReservationStatus.CONSUMED:
                    # Expired grants never cause a chat send to fail or charge a
                    # replacement credit that the player did not authorize.
                    MatchTicket.objects.filter(pk=ticket.pk).update(
                        quota_consumed_at=None, quota_closed_at=timezone.now())
