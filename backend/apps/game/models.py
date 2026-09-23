from django.conf import settings
from django.db import models


class PromptType(models.TextChoices):
    TRUTH = "TRUTH", "حقیقت"
    DARE = "DARE", "جرئت"


class Category(models.TextChoices):
    FRIENDLY = "FRIENDLY", "دوستانه"
    FUNNY = "FUNNY", "خنده‌دار"
    DEEP = "DEEP", "عمیق"
    BOLD = "BOLD", "جسورانه"


class Prompt(models.Model):
    """A question or challenge.

    This table is the product. The engine around it is a few hundred lines;
    whether people keep playing depends on whether these are worth answering.

    Dares are written to be performable *in a text room* — "describe", "tell
    someone", "write it in a strange way". A dare that requires standing up and
    doing something physical cannot be witnessed by strangers in a chat, so it
    silently becomes a skip.
    """

    type = models.CharField(max_length=5, choices=PromptType.choices)
    text = models.TextField(unique=True)
    category = models.CharField(
        max_length=10, choices=Category.choices, default=Category.FRIENDLY
    )
    # 1 safe with strangers · 2 personal · 3 bold. The room picks a ceiling;
    # the engine never serves above it.
    intensity = models.PositiveSmallIntegerField(default=1)
    min_players = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["type", "category", "intensity", "is_active"])]

    def __str__(self) -> str:
        return f"[{self.type}/{self.intensity}] {self.text[:50]}"


class SessionStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "در جریان"
    ENDED = "ENDED", "تمام‌شده"


class TurnStatus(models.TextChoices):
    CHOOSING = "CHOOSING", "در حال انتخاب"
    ANSWERING = "ANSWERING", "در حال پاسخ"
    CONFIRMING = "CONFIRMING", "در انتظار تأیید"
    DONE = "DONE", "انجام شد"
    SKIPPED = "SKIPPED", "رد شد"


class GameSession(models.Model):
    """A game running inside a conversation.

    The foreign key points this way round on purpose: a session belongs to a
    conversation, never the reverse. That is what lets the same engine run for
    strangers matched into a room and for two friends who started a game in the
    middle of their private chat.
    """

    conversation = models.ForeignKey(
        "chat.Conversation", on_delete=models.CASCADE, related_name="game_sessions"
    )
    status = models.CharField(
        max_length=8, choices=SessionStatus.choices, default=SessionStatus.ACTIVE
    )

    # Fixed at start so the order is stable and visible; players who leave are
    # removed from it rather than the order being recomputed each turn.
    turn_order = models.JSONField(default=list)
    turn_index = models.PositiveIntegerField(default=0)
    rounds = models.PositiveSmallIntegerField(default=3)

    category = models.CharField(
        max_length=10, choices=Category.choices, blank=True
    )
    max_intensity = models.PositiveSmallIntegerField(default=2)

    # Avoids repeating a prompt inside one session; across sessions repetition
    # is fine and even welcome.
    used_prompt_ids = models.JSONField(default=list)

    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_reason = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["conversation", "status"])]

    def __str__(self) -> str:
        return f"session {self.pk} in {self.conversation_id} ({self.status})"

    @property
    def total_turns(self) -> int:
        """How many turns this game is expected to run — a display figure.

        Deliberately *not* used to decide when the game ends. It is derived
        from the current player list, so a player leaving shrinks it; an
        earlier version ended the game on `turn_index >= total_turns` and a
        single departure could declare a game finished halfway through.
        Completion is decided per player in `services._is_complete`.
        """
        return len(self.turn_order) * self.rounds


class Turn(models.Model):
    session = models.ForeignKey(
        GameSession, on_delete=models.CASCADE, related_name="turns"
    )
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    index = models.PositiveIntegerField()

    status = models.CharField(
        max_length=10, choices=TurnStatus.choices, default=TurnStatus.CHOOSING
    )
    choice = models.CharField(max_length=5, choices=PromptType.choices, blank=True)
    prompt = models.ForeignKey(Prompt, on_delete=models.SET_NULL, null=True, blank=True)
    answer_message = models.ForeignKey(
        "chat.Message", on_delete=models.SET_NULL, null=True, blank=True
    )

    # Bumped on every transition. Nothing schedules against it any more —
    # turns have no deadlines — but it still makes a repeated confirmation or a
    # double-tapped button identifiable as acting on a turn that already moved.
    version = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("index",)
        constraints = [
            models.UniqueConstraint(
                fields=["session", "index"], name="unique_turn_index"
            )
        ]

    def __str__(self) -> str:
        return f"turn {self.index} of session {self.session_id} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in (
            TurnStatus.CHOOSING,
            TurnStatus.ANSWERING,
            TurnStatus.CONFIRMING,
        )


class TurnConfirmation(models.Model):
    """One player vouching that the turn's player did what was asked.

    A turn moves on because people say it should, never because time passed.
    That is the whole point of the change: a room may sit on one turn for an
    hour while they talk about something else, and nothing should tidy it away
    underneath them.
    """

    turn = models.ForeignKey(
        Turn, on_delete=models.CASCADE, related_name="confirmations"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["turn", "user"], name="unique_turn_confirmation"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} confirmed turn {self.turn_id}"
