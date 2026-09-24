"""Chat business logic.

Everything here is called from both the REST views and the WebSocket consumer.
That is deliberate: sending a message over the socket and sending it over HTTP
must produce the same rows, the same fan-out and the same errors, or the two
paths will quietly diverge and only one of them will be tested.
"""

import logging

from django.db import IntegrityError, transaction
from django.db.models import (
    BigIntegerField,
    Count,
    DateTimeField,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.chat import broadcast
from apps.chat.models import (
    Conversation,
    ConversationStatus,
    ConversationType,
    Message,
    MessageType,
    Participant,
    Reaction,
)
from apps.chat.payloads import conversation_payload, message_payload
from apps.core.errors import DomainError
from apps.users.models import User

logger = logging.getLogger("ft.chat")

PREVIEW_LABELS = {
    MessageType.SYSTEM: "پیام سیستمی",
    MessageType.GAME_PROMPT: "سؤال بازی",
    MessageType.GAME_ANSWER: "پاسخ بازی",
}


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def conversations_for(
    user: User, *, with_participants: bool = False
) -> QuerySet[Conversation]:
    """The user's chat list, with unread counts, in a fixed number of queries.

    The nested subquery is the price of not doing a count per row; this list is
    fetched on nearly every app launch, so an N+1 here is felt immediately.

    `with_participants` prefetches the members as `active_members`. Callers that
    render names and avatars must use it — asking for them per row turned this
    into 41 queries for 20 conversations, and the cost grows with exactly the
    people who use the product most.
    """
    my_participation = Participant.objects.filter(
        conversation=OuterRef("pk"), user=user, left_at__isnull=True
    )

    # Two flat annotations rather than one nested subquery. Nesting the read
    # cursor inside the unread count makes its OuterRef resolve against the
    # message queryset instead of the conversation, which Postgres rejects as
    # `uuid = bigint` — correct, and easy to write by accident.
    conversations = (
        Conversation.objects.filter(
            participants__user=user, participants__left_at__isnull=True
        )
        .annotate(
            last_read=Coalesce(
                Subquery(
                    my_participation.values("last_read_message_id")[:1],
                    output_field=BigIntegerField(),
                ),
                Value(0),
                output_field=BigIntegerField(),
            ),
            my_hidden_at=Subquery(
                my_participation.values("hidden_at")[:1],
                output_field=DateTimeField(),
            ),
        )
        # Deleted by this user and nothing has happened since. A newer message
        # brings the row back, which is what people expect when someone writes
        # to them again after they cleared the chat. Compared against the
        # annotation with F(); OuterRef only resolves inside a subquery.
        .exclude(
            Q(my_hidden_at__isnull=False) & Q(last_message_at__lte=F("my_hidden_at"))
        )
    )

    unread = (
        Message.objects.filter(
            conversation=OuterRef("pk"),
            is_deleted=False,
            id__gt=OuterRef("last_read"),
        )
        .exclude(sender=user)
        .order_by()
        .values("conversation")
        .annotate(total=Count("id"))
        .values("total")
    )

    queryset = conversations.annotate(
        unread_count=Coalesce(Subquery(unread, output_field=IntegerField()), 0)
    ).distinct()

    if with_participants:
        queryset = queryset.prefetch_related(
            Prefetch(
                "participants",
                queryset=Participant.objects.filter(
                    left_at__isnull=True
                ).select_related("user"),
                to_attr="active_members",
            )
        )
    return queryset


def active_participant(user: User, conversation_id) -> Participant:
    participant = Participant.objects.filter(
        conversation_id=conversation_id, user=user, left_at__isnull=True
    ).first()
    if participant is None:
        raise DomainError("not_a_participant", "شما عضو این گفتگو نیستید.", 403)
    return participant


def participant_user_ids(conversation_id) -> list[int]:
    return list(
        Participant.objects.filter(
            conversation_id=conversation_id, left_at__isnull=True
        ).values_list("user_id", flat=True)
    )


def participants_of(conversation_id) -> list[User]:
    return [
        p.user
        for p in Participant.objects.filter(
            conversation_id=conversation_id, left_at__isnull=True
        ).select_related("user")
    ]


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


@transaction.atomic
def create_room(owner: User, max_players: int = 8) -> Conversation:
    conversation = Conversation.objects.create(
        type=ConversationType.ROOM,
        status=ConversationStatus.WAITING,
        code=Conversation.generate_code(),
        max_players=max(2, min(8, max_players)),
        owner=owner,
    )
    Participant.objects.create(conversation=conversation, user=owner)
    logger.info(
        "chat.room_created",
        extra={"event": "chat.room_created", "conversation_id": str(conversation.id)},
    )
    return conversation


@transaction.atomic
def join_by_code(user: User, code: str) -> tuple[Conversation, bool]:
    conversation = (
        Conversation.objects.select_for_update()
        .filter(code=code.strip().upper(), type=ConversationType.ROOM)
        .first()
    )
    if conversation is None:
        raise DomainError("room_not_found", "روم با این کد پیدا نشد.", 404)
    if conversation.status == ConversationStatus.CLOSED:
        raise DomainError("room_closed", "این روم بسته شده است.", 410)

    existing = Participant.objects.filter(conversation=conversation, user=user).first()
    if existing and existing.left_at is None:
        return conversation, False

    active_count = conversation.active_participants.count()
    if active_count >= conversation.max_players:
        raise DomainError("room_full", "ظرفیت روم تکمیل است.", 409)

    # Nobody should be matched into a room with someone they blocked.
    for other in participants_of(conversation.id):
        if user.blocks_or_blocked_by(other):
            raise DomainError(
                "blocked", "امکان ورود به این روم وجود ندارد.", 403
            )

    if existing:
        existing.left_at = None
        existing.save(update_fields=["left_at"])
    else:
        Participant.objects.create(conversation=conversation, user=user)

    transaction.on_commit(
        lambda: post_system_message(
            conversation, f"{user.display_name or user.username} وارد شد."
        )
    )
    return conversation, True


@transaction.atomic
def leave(user: User, conversation: Conversation) -> None:
    participant = active_participant(user, conversation.id)
    participant.left_at = timezone.now()
    participant.save(update_fields=["left_at"])

    # A room outlives the people currently in it. Two players who got on well
    # but have not yet sent a friend request would otherwise lose each other
    # the moment they both closed the tab; the room stays until its owner ends
    # it deliberately.
    if conversation.owner_id == user.pk:
        successor = (
            conversation.active_participants.order_by("joined_at")
            .values_list("user_id", flat=True)
            .first()
        )
        conversation.owner_id = successor
        conversation.save(update_fields=["owner"])

    name = user.display_name or user.username
    transaction.on_commit(lambda: post_system_message(conversation, f"{name} خارج شد."))

    # Imported here rather than at module level: game imports chat, so a
    # top-level import in this direction would be a cycle. Leaving mid-game is
    # a defined transition — the engine drops the player from the turn order
    # and keeps going for everyone else.
    from apps.game import services as game_services

    game_services.on_participant_left(conversation.id, user.pk)


@transaction.atomic
def get_or_create_direct(a: User, b: User) -> Conversation:
    """The private conversation between two people, created once.

    Idempotent on purpose: friendship can be accepted from two devices at once,
    and two DIRECT conversations for the same pair would silently split their
    history in half.
    """
    existing = (
        Conversation.objects.filter(type=ConversationType.DIRECT)
        .filter(participants__user=a)
        .filter(participants__user=b)
        .first()
    )
    if existing:
        return existing

    conversation = Conversation.objects.create(
        type=ConversationType.DIRECT,
        status=ConversationStatus.ACTIVE,
        max_players=2,
    )
    Participant.objects.bulk_create(
        [
            Participant(conversation=conversation, user=a),
            Participant(conversation=conversation, user=b),
        ]
    )
    return conversation


@transaction.atomic
def close_room(user: User, conversation: Conversation) -> Conversation:
    """End a room for everyone. Only its owner may do this.

    Closing is the one way a room ends, so it is a deliberate act by a named
    person rather than a side effect of everyone happening to leave. History
    stays readable afterwards; only new messages stop.
    """
    if conversation.type != ConversationType.ROOM:
        raise DomainError("not_a_room", "این گفتگو روم نیست.", 400)
    if conversation.status == ConversationStatus.CLOSED:
        return conversation
    if conversation.owner_id != user.pk:
        raise DomainError("not_room_owner", "فقط سازنده‌ی روم می‌تواند آن را ببندد.", 403)

    active_participant(user, conversation.id)

    conversation.status = ConversationStatus.CLOSED
    conversation.save(update_fields=["status"])

    from apps.game import services as game_services

    session = game_services.active_session(conversation.id)
    if session is not None:
        game_services.end_game(session, "room_closed")

    logger.info(
        "chat.room_closed",
        extra={
            "event": "chat.room_closed",
            "conversation_id": str(conversation.id),
            "user_id": user.pk,
        },
    )

    post_system_message(conversation, "روم بسته شد.", meta={"room": "closed"})
    recipients = participant_user_ids(conversation.id)
    transaction.on_commit(
        lambda: broadcast.to_users(
            recipients, "conv.updated", conversation_payload(conversation)
        )
    )
    return conversation


@transaction.atomic
def delete_for_me(user: User, conversation: Conversation) -> None:
    """Remove a conversation from one person's list.

    Nothing is destroyed. The other side keeps the room and every message in
    it, because those messages are theirs too — a delete that reached into
    someone else's history would be a way to erase evidence, not a tidy-up.

    Leaving a room as well as hiding it is deliberate: a room you deleted
    should stop involving you, and you kept the code if you want back in. A
    private chat only hides, so the other person can still reach you.
    """
    participant = active_participant(user, conversation.id)

    last_id = (
        Message.objects.filter(conversation=conversation)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
        or 0
    )
    participant.hidden_at = timezone.now()
    participant.cleared_before_id = last_id
    participant.save(update_fields=["hidden_at", "cleared_before_id"])

    logger.info(
        "chat.conversation_deleted",
        extra={
            "event": "chat.conversation_deleted",
            "conversation_id": str(conversation.id),
            "user_id": user.pk,
        },
    )

    if conversation.type == ConversationType.ROOM:
        leave(user, conversation)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def _preview_for(message: Message) -> str:
    if message.type == MessageType.TEXT:
        return message.body[:120]
    return PREVIEW_LABELS.get(message.type, "")[:120]


def post_message(
    *,
    conversation: Conversation,
    sender: User | None,
    body: str,
    client_id: str = "",
    message_type: str = MessageType.TEXT,
    reply_to_id: int | None = None,
    meta: dict | None = None,
) -> tuple[Message, bool]:
    """Append a message and fan it out. Returns (message, created).

    `created=False` means this exact client_id was already stored — a retry
    after a dropped connection, not a second message. Returning the original
    instead of raising lets the client reconcile its optimistic bubble either
    way.
    """
    # A closed room keeps its history but takes no new lines. System messages
    # are exempt so the closing notice itself can be written.
    if (
        conversation.status == ConversationStatus.CLOSED
        and message_type != MessageType.SYSTEM
    ):
        raise DomainError("room_closed", "این روم بسته شده است.", 410)

    body = (body or "").strip()
    if message_type == MessageType.TEXT and not body:
        raise DomainError("empty_message", "پیام خالی است.")
    if len(body) > 2000:
        raise DomainError("message_too_long", "پیام خیلی طولانی است.")

    # Imported here rather than at module level: moderation imports chat.
    from apps.moderation import filters
    from apps.moderation import services as moderation

    if sender is not None:
        moderation.assert_not_blocked(sender, conversation)

        # Applied to what people write, not to what the game writes.
        result = filters.screen(body)
        if result.blocked:
            raise DomainError(
                "message_rejected",
                "این پیام قابل ارسال نیست.",
                422,
            )
        if result.masked:
            logger.info(
                "moderation.message_masked",
                extra={
                    "event": "moderation.message_masked",
                    "conversation_id": str(conversation.id),
                    "sender_id": sender.pk,
                },
            )
        body = result.text

    if reply_to_id is not None and not Message.objects.filter(
        pk=reply_to_id, conversation=conversation
    ).exists():
        raise DomainError("bad_reply", "پیام مرجع پیدا نشد.")

    try:
        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                sender=sender,
                type=message_type,
                body=body,
                client_id=client_id or "",
                reply_to_id=reply_to_id,
                meta=meta or {},
            )
    except IntegrityError:
        existing = Message.objects.filter(
            conversation=conversation, client_id=client_id
        ).first()
        if existing is None:
            raise
        return existing, False

    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=message.created_at,
        last_message_preview=_preview_for(message),
    )
    conversation.last_message_at = message.created_at
    conversation.last_message_preview = _preview_for(message)

    # A message created a millisecond ago cannot have reactions yet. Saying so
    # here spares `message_payload` a SELECT on the busiest path in the app.
    message._prefetched_objects_cache = {"reactions": Reaction.objects.none()}

    recipients = participant_user_ids(conversation.id)
    payload = message_payload(message)
    broadcast.to_users(recipients, "chat.message", payload)
    # A second, lighter event so a client showing only the chat list does not
    # have to keep every conversation's message state to reorder the list.
    broadcast.to_users(
        recipients,
        "conv.updated",
        conversation_payload(conversation),
    )

    logger.info(
        "chat.message_sent",
        extra={
            "event": "chat.message_sent",
            "conversation_id": str(conversation.id),
            "message_id": message.pk,
            "sender_id": sender.pk if sender else None,
        },
    )
    return message, True


def post_system_message(conversation: Conversation, body: str, meta: dict | None = None):
    return post_message(
        conversation=conversation,
        sender=None,
        body=body,
        message_type=MessageType.SYSTEM,
        meta=meta,
    )[0]


def history(
    conversation: Conversation,
    *,
    before: int | None = None,
    after: int | None = None,
    limit: int = 50,
    cleared_before_id: int = 0,
) -> list[Message]:
    """Cursor pagination in both directions.

    `after` is the reconnect path: a client that lost its socket asks for
    everything newer than the last id it holds, which is why message ids are
    monotonic integers rather than timestamps.
    """
    limit = max(1, min(100, limit))
    queryset = (
        Message.objects.filter(conversation=conversation, id__gt=cleared_before_id)
        .select_related("sender")
        .prefetch_related("reactions")
    )

    if after is not None:
        return list(queryset.filter(id__gt=after).order_by("id")[:limit])

    if before is not None:
        queryset = queryset.filter(id__lt=before)
    # Newest-first for the page query, then flipped so callers always receive
    # messages in reading order.
    return list(reversed(queryset.order_by("-id")[:limit]))


def mark_read(user: User, conversation_id, up_to_message_id: int) -> int:
    participant = active_participant(user, conversation_id)
    if up_to_message_id <= participant.last_read_message_id:
        return participant.last_read_message_id

    participant.last_read_message_id = up_to_message_id
    participant.save(update_fields=["last_read_message_id"])

    broadcast.to_conversation(
        conversation_id,
        "chat.read",
        {
            "conversation_id": str(conversation_id),
            "user_id": user.pk,
            "up_to_message_id": up_to_message_id,
        },
    )
    return up_to_message_id


def set_reaction(user: User, message_id: int, emoji: str, op: str) -> dict:
    message = Message.objects.filter(pk=message_id).select_related("conversation").first()
    if message is None:
        raise DomainError("message_not_found", "پیام پیدا نشد.", 404)

    active_participant(user, message.conversation_id)

    emoji = (emoji or "").strip()
    if not emoji or len(emoji) > 8:
        raise DomainError("bad_emoji", "واکنش نامعتبر است.")

    if op == "remove":
        Reaction.objects.filter(message=message, user=user, emoji=emoji).delete()
    else:
        op = "add"
        Reaction.objects.get_or_create(message=message, user=user, emoji=emoji)

    payload = {
        "conversation_id": str(message.conversation_id),
        "message_id": message.pk,
        "user_id": user.pk,
        "emoji": emoji,
        "op": op,
    }
    broadcast.to_users(participant_user_ids(message.conversation_id), "chat.reaction", payload)
    return payload
