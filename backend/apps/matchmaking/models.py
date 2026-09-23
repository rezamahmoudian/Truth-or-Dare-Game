from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.game.models import Category
from apps.users.models import Gender


class MatchMode(models.Model):
    """A row per way to start a game.

    Modes are data, not code. The owner intends to keep adding them, and this
    app ships as an installed APK — a hardcoded list would mean a store release
    for every new mode. The frontend renders whatever this table returns.
    """

    key = models.SlugField(max_length=32, unique=True)
    title = models.CharField(max_length=40)
    subtitle = models.CharField(max_length=80, blank=True)
    emoji = models.CharField(max_length=8, blank=True)
    accent = models.CharField(max_length=16, default="brand")

    size_min = models.PositiveSmallIntegerField(default=2)
    size_max = models.PositiveSmallIntegerField(default=2)

    # Blank means "anyone". Set to F or M for the gender-filtered modes.
    target_gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)

    category = models.CharField(max_length=10, choices=Category.choices, blank=True)
    max_intensity = models.PositiveSmallIntegerField(default=2)
    rounds = models.PositiveSmallIntegerField(default=3)

    min_age = models.PositiveSmallIntegerField(default=18)
    requires_premium = models.BooleanField(default=False)
    # Daily cap. The scarce-direction gender queue is the one that starves, and
    # an uncapped free filter is what starves it — see the notes in seed.
    daily_limit = models.PositiveSmallIntegerField(default=0)

    # After this long in the queue the constraints are relaxed and the user is
    # told. An unbounded wait in a filtered queue is the most common way these
    # products lose a first-time user.
    widen_after_seconds = models.PositiveSmallIntegerField(default=20)

    # Drives layout: featured modes are rendered large. Traffic should flow to
    # the queues that actually fill.
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ("sort_order", "key")

    def __str__(self) -> str:
        return f"{self.key} ({self.title})"


class TicketState(models.TextChoices):
    QUEUED = "QUEUED", "در صف"
    MATCHED = "MATCHED", "جور شد"
    CANCELLED = "CANCELLED", "لغو شد"
    EXPIRED = "EXPIRED", "منقضی شد"


class MatchTicket(models.Model):
    """One person's request to be matched.

    Tickets live in Postgres rather than only in Redis: a Redis flush while
    people are queued would leave the database believing they are still
    waiting, and reconciling two sources of truth about who is in a queue is
    worse than the read cost of querying one. Redis still holds the matcher
    lock, which is the part that actually prevents split rooms.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="match_tickets"
    )
    mode = models.ForeignKey(MatchMode, on_delete=models.CASCADE)

    # Snapshotted at enqueue so a profile edit mid-queue cannot change what the
    # matcher already promised other people.
    my_gender = models.CharField(max_length=1, blank=True)
    want_gender = models.CharField(max_length=1, blank=True)
    size_min = models.PositiveSmallIntegerField(default=2)
    size_max = models.PositiveSmallIntegerField(default=2)
    category = models.CharField(max_length=10, blank=True)

    state = models.CharField(
        max_length=10, choices=TicketState.choices, default=TicketState.QUEUED
    )
    widened = models.BooleanField(default=False)
    conversation = models.ForeignKey(
        "chat.Conversation", on_delete=models.SET_NULL, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["state", "created_at"])]
        constraints = [
            # One live request per person. Without this, a client that
            # reconnects and re-enqueues would sit in the queue twice and could
            # be matched into two rooms at once.
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(state="QUEUED"),
                name="one_active_ticket_per_user",
            )
        ]

    def __str__(self) -> str:
        return f"ticket {self.pk} {self.user_id} → {self.mode_id} ({self.state})"
