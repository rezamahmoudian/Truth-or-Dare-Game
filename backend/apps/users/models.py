import hashlib
import secrets
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def hash_device_token(raw_token: str) -> str:
    """Hash a device token for storage.

    The device token is a bearer credential: whoever holds it *is* that guest
    account. Storing it in plain text would mean a database leak hands over
    every guest session, so only the digest is kept — the same reasoning as a
    password, minus the need for a slow KDF since the token is high-entropy
    random rather than human-chosen.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class Gender(models.TextChoices):
    FEMALE = "F", "زن"
    MALE = "M", "مرد"


# Preset avatars rather than uploads. Phase 1 has no image moderation, and a
# stranger-matching product with unmoderated profile photos is a liability the
# moment it has users. Uploads can come later, behind the phase 6 tooling.
AVATAR_CHOICES = [(f"a{i}", f"آواتار {i}") for i in range(1, 13)]


class User(AbstractUser):
    """Application user.

    A user starts as a guest — no signup, no password, identified only by a
    random token held in the browser — and can later upgrade to a permanent
    account. Guest-first entry exists because this product spreads by shared
    links: a signup wall in front of a game invitation loses most of the people
    who clicked it.
    """

    # --- identity ---------------------------------------------------------
    display_name = models.CharField("نام نمایشی", max_length=32, blank=True)
    avatar = models.CharField(max_length=8, choices=AVATAR_CHOICES, blank=True)
    bio = models.CharField(max_length=160, blank=True)

    # --- matchmaking attributes -------------------------------------------
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    # Gender-filtered match modes are only meaningful if gender is stable;
    # unlimited edits turn the filter into a suggestion.
    gender_change_count = models.PositiveSmallIntegerField(default=0)

    # Stored rather than derived from a submitted age so the 18+ gate cannot be
    # re-passed by simply claiming a different number next session.
    birth_date = models.DateField(null=True, blank=True)

    # --- guest session ----------------------------------------------------
    is_guest = models.BooleanField(default=True)
    device_token_hash = models.CharField(
        max_length=64, unique=True, null=True, blank=True, db_index=True
    )

    last_seen_at = models.DateTimeField(null=True, blank=True)

    # Consecutive days on which this person played. Shown in the header, so it
    # has to be a real number — a decorative counter that does not track
    # anything is the kind of detail people notice and stop trusting.
    streak_days = models.PositiveIntegerField(default=0)
    last_played_on = models.DateField(null=True, blank=True)

    class Meta(AbstractUser.Meta):
        db_table = "users_user"

    def __str__(self) -> str:
        return self.display_name or self.username

    # --- derived ----------------------------------------------------------

    @property
    def age(self) -> int | None:
        if not self.birth_date:
            return None
        today = date.today()
        had_birthday = (today.month, today.day) >= (
            self.birth_date.month,
            self.birth_date.day,
        )
        return today.year - self.birth_date.year - (0 if had_birthday else 1)

    @property
    def is_onboarded(self) -> bool:
        """Whether the profile carries everything matchmaking needs."""
        return bool(self.display_name and self.gender and self.birth_date)

    @property
    def can_change_gender(self) -> bool:
        return self.gender_change_count < settings.MAX_GENDER_CHANGES

    def touch_last_seen(self) -> None:
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])

    def record_play(self) -> None:
        """Count today towards the streak.

        Same day is a no-op, yesterday extends, anything older starts again.
        """
        today = timezone.localdate()
        if self.last_played_on == today:
            return
        yesterday = today - timedelta(days=1)
        self.streak_days = self.streak_days + 1 if self.last_played_on == yesterday else 1
        self.last_played_on = today
        self.save(update_fields=["streak_days", "last_played_on"])

    # --- safety -----------------------------------------------------------

    def blocks_or_blocked_by(self, other: "User") -> bool:
        """A block is one-way to create and two-way in effect.

        The person who blocked should not hear from the other, and the person
        blocked should not be able to reach them — so both directions are
        checked wherever two users would be put in contact.
        """
        return Block.objects.filter(
            models.Q(blocker=self, blocked=other) | models.Q(blocker=other, blocked=self)
        ).exists()

    # --- factory ----------------------------------------------------------

    @classmethod
    def generate_username(cls) -> str:
        """A unique, unguessable-enough handle for a brand new guest.

        Guests get a throwaway handle so the account is usable before the person
        has chosen anything; they can claim a real one during onboarding.
        """
        for _ in range(10):
            candidate = f"user_{secrets.token_hex(4)}"
            if not cls.objects.filter(username=candidate).exists():
                return candidate
        raise RuntimeError("could not allocate a unique username")


class Block(models.Model):
    """A one-way block that is enforced in both directions.

    Defined now, before there is a UI for it, because blocking has to be
    consulted by matchmaking and by direct-conversation creation from the day
    those exist — and adding the table later means backfilling against live
    conversations.
    """

    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocks_made")
    blocked = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="blocks_received"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="unique_block"),
            models.CheckConstraint(
                condition=~models.Q(blocker=models.F("blocked")),
                name="no_self_block",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.blocker_id} → {self.blocked_id}"


class ReportReason(models.TextChoices):
    HARASSMENT = "HARASSMENT", "آزار و توهین"
    SEXUAL = "SEXUAL", "محتوای جنسی"
    SPAM = "SPAM", "تبلیغ و اسپم"
    UNDERAGE = "UNDERAGE", "کاربر زیر سن قانونی"
    OTHER = "OTHER", "سایر"


class ReportStatus(models.TextChoices):
    OPEN = "OPEN", "بررسی‌نشده"
    REVIEWED = "REVIEWED", "بررسی‌شده"
    ACTIONED = "ACTIONED", "اقدام شد"


class Report(models.Model):
    """A report against a user, optionally pointing at a specific message."""

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reports_made")
    target_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reports_received"
    )
    target_message = models.ForeignKey(
        "chat.Message", on_delete=models.SET_NULL, null=True, blank=True
    )
    reason = models.CharField(max_length=16, choices=ReportReason.choices)
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=10, choices=ReportStatus.choices, default=ReportStatus.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.reason} against {self.target_user_id} ({self.status})"


class FriendshipStatus(models.TextChoices):
    PENDING = "PENDING", "در انتظار"
    ACCEPTED = "ACCEPTED", "دوست"
    DECLINED = "DECLINED", "رد شده"


class Friendship(models.Model):
    """A friend request and, once accepted, the friendship itself.

    One row for the pair rather than two mirrored rows: a friendship is
    symmetric, and two rows means two places for it to get out of sync. The
    direction is kept only because it decides who sees an "accept" button.

    This is the hinge of the product. The game exists to produce this row; the
    private conversation it creates is what people come back for.
    """

    from_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="friend_requests_sent"
    )
    to_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="friend_requests_received"
    )
    status = models.CharField(
        max_length=8, choices=FriendshipStatus.choices, default=FriendshipStatus.PENDING
    )

    # The DIRECT conversation opened when the request was accepted.
    conversation = models.ForeignKey(
        "chat.Conversation", on_delete=models.SET_NULL, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_user"], name="unique_friendship_direction"
            ),
            models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="no_self_friendship",
            ),
        ]
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return f"{self.from_user_id} → {self.to_user_id} ({self.status})"

    def other_than(self, user_id: int) -> User:
        return self.to_user if self.from_user_id == user_id else self.from_user
