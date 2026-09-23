import secrets
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

# Ambiguous glyphs removed: these codes get read aloud and retyped from a
# screenshot, where O/0 and I/1 cost more than the lost entropy.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


class ConversationType(models.TextChoices):
    ROOM = "ROOM", "روم بازی"
    DIRECT = "DIRECT", "چت خصوصی"


class ConversationStatus(models.TextChoices):
    WAITING = "WAITING", "در انتظار بازیکن"
    ACTIVE = "ACTIVE", "فعال"
    CLOSED = "CLOSED", "بسته"


class MessageType(models.TextChoices):
    TEXT = "TEXT", "متن"
    SYSTEM = "SYSTEM", "سیستمی"
    GAME_PROMPT = "GAME_PROMPT", "سؤال بازی"
    GAME_ANSWER = "GAME_ANSWER", "پاسخ بازی"


class Conversation(models.Model):
    """A single chat context — a match room or a private conversation.

    One model for both because the alternative (separate "room chat" and
    "private chat" systems) means writing unread counts, typing indicators,
    reactions, pagination and moderation twice, and watching them drift apart.
    A game session attaches to one of these; it does not own it.
    """

    # UUID because conversation ids travel in shareable links.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=8, choices=ConversationType.choices)
    status = models.CharField(
        max_length=8, choices=ConversationStatus.choices, default=ConversationStatus.ACTIVE
    )

    code = models.CharField(max_length=CODE_LENGTH, unique=True, null=True, blank=True)
    max_players = models.PositiveSmallIntegerField(default=8)

    # Whoever opened the room — the person who created it, or the first of a
    # matched group. A room stays open until they close it, so this has to be
    # someone specific rather than "whoever is around": if the owner leaves,
    # ownership passes to the longest-present remaining player, otherwise the
    # close button belongs to nobody and the room can never be shut.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_conversations",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # Denormalised so the chat list — the most-opened screen in the app —
    # renders from one query instead of one per row.
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ("-last_message_at", "-created_at")
        indexes = [models.Index(fields=["type", "status"])]

    def __str__(self) -> str:
        return f"{self.type} {self.code or self.id}"

    @classmethod
    def generate_code(cls) -> str:
        for _ in range(20):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if not cls.objects.filter(code=code).exists():
                return code
        raise RuntimeError("could not allocate a unique room code")

    @property
    def active_participants(self):
        return self.participants.filter(left_at__isnull=True)


class Participant(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="participations"
    )

    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    # Message ids are bigints precisely so this is an integer comparison rather
    # than a timestamp range or a join table of read receipts.
    last_read_message_id = models.BigIntegerField(default=0)

    # "Delete chat" is per person. The other side keeps the conversation and
    # every message in it — deleting your copy must never reach into someone
    # else's history. Messages at or below the cursor are hidden from this
    # user, and the row reappears in their list if a newer one arrives, which
    # is what people expect when someone writes to them again.
    hidden_at = models.DateTimeField(null=True, blank=True)
    cleared_before_id = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "user"], name="unique_participant"
            )
        ]
        indexes = [models.Index(fields=["user", "left_at"])]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.conversation_id}"


class Message(models.Model):
    """A line in a conversation — typed by a person or emitted by the game.

    Game events are messages rather than a parallel event stream because the
    product's whole premise is that the game exists to start conversations. A
    prompt and its answer belong in the same scroll as the replies they
    provoke, not in a separate pane beside them.
    """

    # BigAutoField (the project default): unread counts and cursor pagination
    # both reduce to integer comparison.
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    type = models.CharField(
        max_length=12, choices=MessageType.choices, default=MessageType.TEXT
    )
    body = models.TextField(max_length=2000, blank=True)
    reply_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies"
    )

    # Echoed back to the sender so an optimistically-rendered bubble can be
    # reconciled, and unique per conversation so a retry after a dropped
    # connection cannot produce a duplicate.
    client_id = models.CharField(max_length=40, blank=True)

    # Structured payload for game events; ordinary chat leaves it empty.
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ("id",)
        indexes = [models.Index(fields=["conversation", "id"])]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "client_id"],
                condition=~Q(client_id=""),
                name="unique_client_message",
            )
        ]

    def __str__(self) -> str:
        return f"#{self.pk} {self.body[:30]}"


class Reaction(models.Model):
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="reactions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reactions"
    )
    emoji = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user", "emoji"], name="unique_reaction"
            )
        ]

    def __str__(self) -> str:
        return f"{self.emoji} on #{self.message_id}"
