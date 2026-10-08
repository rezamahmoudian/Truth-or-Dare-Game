import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.chat import broadcast
from apps.chat import services as chat
from apps.chat.models import (
    Conversation,
    ConversationStatus,
    ConversationType,
    Message,
    Participant,
)
from apps.core.errors import DomainError
from apps.game import services as game
from apps.game.models import TurnStatus
from apps.users.models import User

from .models import AIConversation, AIEncounter, AISettings, DailyUsage, Persona

logger = logging.getLogger("ft.ai")


def available():
    return bool(settings.AI_PLAYERS_ENABLED and settings.OPENAI_API_KEY)


def assert_available(user):
    if not available():
        raise DomainError("ai_unavailable", "بازی هنوز فعال نشده است.", 503)
    if user.is_ai or not user.is_active or not user.is_onboarded or user.age is None or user.age < 18:
        raise DomainError("ai_not_allowed", "برای بازی پروفایل بزرگسال خود را کامل کنید.", 403)
    day = timezone.localdate()
    for key, limit in [(0, settings.AI_DAILY_REQUEST_LIMIT), (user.pk, settings.AI_USER_DAILY_REQUEST_LIMIT)]:
        if DailyUsage.objects.filter(day=day, user_key=key, requests__gte=limit).exists() or limit <= 0:
            raise DomainError("ai_daily_limit", "سهمیهٔ امروز بازی شما تمام شده است.", 429)


def eligible_personas(user):
    rows = Persona.objects.filter(is_active=True, user__is_active=True).select_related("user")
    blocked = user.blocks_made.values_list("blocked_id", flat=True)
    blockers = user.blocks_received.values_list("blocker_id", flat=True)
    encountered = AIEncounter.objects.filter(human=user).values_list("persona_id", flat=True)
    return rows.exclude(user_id__in=blocked).exclude(user_id__in=blockers).exclude(pk__in=encountered)


@transaction.atomic
def match_ticket(ticket):
    """Called inside the central matcher, after human matches for fallback tickets."""
    from apps.matchmaking.models import MatchTicket, TicketState

    ticket = MatchTicket.objects.select_for_update().select_related("user", "mode").get(pk=ticket.pk)
    if ticket.state != TicketState.QUEUED:
        return False
    if (ticket.size_min, ticket.size_max) != (2, 2):
        return False
    if ticket.mode.is_ai and not ticket.ai_consent:
        return False
    if not ticket.mode.is_ai and (not AISettings.load().fallback_enabled
                                 or not ticket.ai_fallback_at or ticket.ai_fallback_at > timezone.now()):
        return False
    # The DB lock also protects against an expired central Redis lease.
    User.objects.select_for_update().get(pk=ticket.user_id)
    try:
        assert_available(ticket.user)
    except DomainError:
        if not ticket.mode.is_ai:
            return False
        ticket.state = TicketState.CANCELLED
        ticket.save(update_fields=["state"])
        transaction.on_commit(lambda: broadcast.to_users([ticket.user_id], "mm.cancelled", {}))
        return False
    candidates = eligible_personas(ticket.user)
    if ticket.want_gender:
        candidates = candidates.filter(gender=ticket.want_gender)
    persona = candidates.order_by("?").first()
    if not persona:
        # Exhaustion is per user and permanent. Do not probe the provider or
        # take an automatic-fallback ticket out of the human matchmaking queue.
        return False
    from .readiness import ready_for_ticket
    # Probe asynchronously: no network waits under the matcher/DB locks. A
    # missing worker, timeout or unknown health never authorizes a new room.
    if not ready_for_ticket(ticket):
        return False
    # The human row lock serializes selection and durable encounter creation.
    # A new ticket must never reopen a room with a previously encountered persona.
    conversation = Conversation.objects.create(type=ConversationType.ROOM, status=ConversationStatus.ACTIVE,
                                               owner=ticket.user, max_players=2)
    Participant.objects.bulk_create([Participant(conversation=conversation, user=ticket.user),
                                     Participant(conversation=conversation, user=persona.user)])
    AIConversation.objects.create(conversation=conversation, human=ticket.user, persona=persona)
    notify(conversation.pk)
    ticket.state, ticket.conversation = TicketState.MATCHED, conversation
    ticket.save(update_fields=["state", "conversation"])
    transaction.on_commit(lambda: broadcast.to_users([ticket.user_id], "mm.matched", {
        "conversation_id": str(conversation.pk), "mode": ticket.mode.key,
        "player_ids": [ticket.user_id, persona.user_id],
    }))
    return True


def valid(state):
    if state.expires_at <= timezone.now():
        return False
    if not available() or not state.persona.is_active or not state.persona.user.is_active:
        return False
    if state.conversation.status == ConversationStatus.CLOSED or not state.human.is_active:
        return False
    if state.human.age is None or state.human.age < 18 or state.human.blocks_or_blocked_by(state.persona.user):
        return False
    members = set(Participant.objects.filter(conversation_id=state.pk, left_at__isnull=True).values_list("user_id", flat=True))
    return members == {state.human_id, state.persona.user_id}


def assert_session_open(conversation_id):
    if AIConversation.objects.filter(pk=conversation_id, expires_at__lte=timezone.now()).exists():
        raise DomainError("ai_session_ended", "زمان این گفتگو تمام شده است.", 410)


@transaction.atomic
def expire_session(conversation_id):
    state = AIConversation.objects.select_for_update().filter(pk=conversation_id).first()
    if not state or state.expires_at > timezone.now():
        return False
    conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
    if conversation.status == ConversationStatus.CLOSED:
        return False
    conversation.status = ConversationStatus.CLOSED
    conversation.save(update_fields=["status"])
    state.handled_revision = state.revision
    state.lease = state.lease_until = state.retry_at = None
    state.save(update_fields=["handled_revision", "lease", "lease_until", "retry_at"])
    session = game.active_session(conversation_id)
    if session:
        game.end_game(session, "ai_time_limit")
    chat.post_system_message(conversation, "گفتگو بسته شد و پیام‌ها باقی می‌مانند.",
                             meta={"room": "closed", "ai_session_ended": True})
    from apps.chat.payloads import conversation_payload
    recipients = chat.participant_user_ids(conversation_id)
    transaction.on_commit(lambda: broadcast.to_users(recipients, "conv.updated", conversation_payload(conversation)))
    return True


def notify(conversation_id):
    """Persist before queueing, including while the provider is disabled."""
    if AIConversation.objects.filter(pk=conversation_id).update(revision=F("revision") + 1):
        transaction.on_commit(lambda: dispatch(conversation_id))


def dispatch(conversation_id, *, eta=None):
    if not available():
        return
    from .tasks import respond
    try:
        if eta is None:
            respond.delay(str(conversation_id))
        else:
            respond.apply_async(args=[str(conversation_id)], eta=eta)
    except (OperationalError, OSError):
        # Beat will redeliver durable pending work; a broker failure must not
        # turn a successfully saved human message into an apparent send failure.
        logger.warning("ai.queue_unavailable")


def schedule_delivery(request_id, deliver_at):
    from .tasks import deliver
    try:
        deliver.apply_async(args=[str(request_id)], eta=deliver_at)
    except (OperationalError, OSError):
        # The response and deadline are durable; beat can enqueue them again.
        logger.warning("ai.delivery_queue_unavailable")


def snapshot(state):
    session = game.active_session(state.pk)
    turn = game.current_turn(session) if session else None
    signature = (turn.pk, turn.version, turn.status) if turn else None
    action = "chat"
    if turn and turn.player_id == state.persona.user_id:
        if turn.status == TurnStatus.CHOOSING:
            action = "choose"
        elif turn.status == TurnStatus.ANSWERING:
            action = "answer"
    elif turn and turn.status == TurnStatus.CONFIRMING:
        action = "confirm"
    messages = Message.objects.filter(conversation_id=state.pk, is_deleted=False)
    latest_id = messages.order_by("-id").values_list("id", flat=True).first()
    latest = messages.filter(sender__isnull=False).order_by("-id").first()
    last_reply_id = (messages.filter(sender_id=state.persona.user_id)
                     .order_by("-id").values_list("id", flat=True).first() or 0)
    # Keep the whole unanswered burst, even if it exceeds the background history limit.
    pending = list(messages.filter(sender_id=state.human_id, id__gt=last_reply_id).order_by("id"))
    rows = list(messages.exclude(sender_id=state.human_id, id__gt=last_reply_id)
                .order_by("-id")[:max(1, min(settings.AI_HISTORY_MESSAGES, 40))])
    if action == "chat" and latest and latest.sender_id == state.persona.user_id:
        action = "wait"
    batch_ready_at = (pending[-1].created_at + timedelta(seconds=max(0, settings.AI_MESSAGE_BATCH_SECONDS))
                      if pending else None)
    context = {
        "latest_message_id": latest_id,
        "batch_ready_at": batch_ready_at.isoformat() if batch_ready_at else None,
        "pending_user_messages": [
            {"text": m.body, "attachment": m.attachment_info.get("kind") if m.attachment else None}
            for m in pending
        ],
        "history": [{"speaker": "self" if m.sender_id == state.persona.user_id else "player" if m.sender_id else "game",
                     "text": m.body[:1200], "attachment": m.attachment_info.get("kind") if m.attachment else None}
                    for m in reversed(rows)],
        "turn": {"state": turn.status, "mine": turn.player_id == state.persona.user_id,
                 "prompt": turn.prompt.text if turn.prompt else None} if turn else None,
    }
    return action, signature, context


def reserve_usage(user_id):
    """Count attempts, including provider failures, under a global DB lock."""
    for key, limit in [(0, settings.AI_DAILY_REQUEST_LIMIT), (user_id, settings.AI_USER_DAILY_REQUEST_LIMIT)]:
        row, _ = DailyUsage.objects.get_or_create(day=timezone.localdate(), user_key=key)
        row = DailyUsage.objects.select_for_update().get(pk=row.pk)
        if row.requests >= limit:
            raise DomainError("ai_daily_limit", "سهمیهٔ ی جستجوی سریع تمام شده است ممکن است برای پیدا شدن هم بازی کمی منتظر بمانید.", 429)
        row.requests += 1
        row.save(update_fields=["requests"])


def pending_ids():
    now = timezone.now()
    return (AIConversation.objects.filter(revision__gt=F("handled_revision"))
            .filter(Q(lease_until__isnull=True) | Q(lease_until__lt=now))
            .filter(Q(retry_at__isnull=True) | Q(retry_at__lte=now))
            .values_list("pk", flat=True)[:100])
