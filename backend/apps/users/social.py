"""Friendship.

The product's whole loop converges here: a random game produces a friend
request, accepting it opens a private conversation, and that conversation is
what brings someone back on day ten. Everything in this module is one step of
that chain.
"""

import logging

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.chat import broadcast
from apps.chat import services as chat_services
from apps.core.errors import DomainError
from apps.users.models import Friendship, FriendshipStatus, User

logger = logging.getLogger("ft.social")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def _pair(a: User, b: User):
    return Friendship.objects.filter(
        Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a)
    ).first()


def friendship_with(user: User, other: User) -> Friendship | None:
    return _pair(user, other)


def friends_of(user: User) -> list[User]:
    rows = (
        Friendship.objects.filter(
            Q(from_user=user) | Q(to_user=user), status=FriendshipStatus.ACCEPTED
        )
        .select_related("from_user", "to_user")
        .order_by("-responded_at")
    )
    return [row.other_than(user.pk) for row in rows]


def incoming_requests(user: User) -> list[Friendship]:
    return list(
        Friendship.objects.filter(to_user=user, status=FriendshipStatus.PENDING)
        .select_related("from_user")
        .order_by("-created_at")
    )


def outgoing_requests(user: User) -> list[Friendship]:
    return list(
        Friendship.objects.filter(from_user=user, status=FriendshipStatus.PENDING)
        .select_related("to_user")
        .order_by("-created_at")
    )


def relation_to(user: User, other: User) -> str:
    """What the button on someone's profile should say."""
    if user.pk == other.pk:
        return "SELF"
    if user.blocks_or_blocked_by(other):
        return "BLOCKED"

    row = _pair(user, other)
    if row is None:
        return "NONE"
    if row.status == FriendshipStatus.ACCEPTED:
        return "FRIENDS"
    if row.status == FriendshipStatus.PENDING:
        return "OUTGOING" if row.from_user_id == user.pk else "INCOMING"
    return "NONE"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _resolve(user: User, other_id: int) -> User:
    other = User.objects.filter(pk=other_id, is_active=True).first()
    if other is None:
        raise DomainError("user_not_found", "کاربر پیدا نشد.", 404)
    if other.pk == user.pk:
        raise DomainError("self_request", "نمی‌توانید به خودتان درخواست بدهید.", 400)
    if user.blocks_or_blocked_by(other):
        raise DomainError("blocked", "امکان ارتباط با این کاربر وجود ندارد.", 403)
    return other


@transaction.atomic
def send_request(user: User, other_id: int) -> Friendship:
    other = _resolve(user, other_id)
    existing = _pair(user, other)

    if existing and existing.status == FriendshipStatus.ACCEPTED:
        return existing

    # They asked first and we are asking back — that is an acceptance, not a
    # second request. Making the user find the other person's pending request
    # to press "accept" would be a confusing dead end.
    if (
        existing
        and existing.status == FriendshipStatus.PENDING
        and existing.to_user_id == user.pk
    ):
        return accept_request(user, other.pk)

    if existing:
        existing.from_user, existing.to_user = user, other
        existing.status = FriendshipStatus.PENDING
        existing.responded_at = None
        existing.save(update_fields=["from_user", "to_user", "status", "responded_at"])
        friendship = existing
    else:
        try:
            friendship = Friendship.objects.create(from_user=user, to_user=other)
        except IntegrityError:
            found = _pair(user, other)
            if found is None:
                raise
            return found

    logger.info(
        "social.request_sent",
        extra={"event": "social.request_sent", "user_id": user.pk, "target": other.pk},
    )
    transaction.on_commit(
        lambda: broadcast.to_users(
            [other.pk], "friend.request", {"from_user": _user_payload(user)}
        )
    )
    return friendship


@transaction.atomic
def accept_request(user: User, other_id: int) -> Friendship:
    other = _resolve(user, other_id)
    row = Friendship.objects.filter(
        from_user=other, to_user=user, status=FriendshipStatus.PENDING
    ).first()
    if row is None:
        raise DomainError("no_request", "درخواستی از این کاربر وجود ندارد.", 404)

    conversation = chat_services.get_or_create_direct(user, other)

    row.status = FriendshipStatus.ACCEPTED
    row.responded_at = timezone.now()
    row.conversation = conversation
    row.save(update_fields=["status", "responded_at", "conversation"])

    logger.info(
        "social.request_accepted",
        extra={
            "event": "social.request_accepted",
            "user_id": user.pk,
            "target": other.pk,
            "conversation_id": str(conversation.id),
        },
    )

    # Opened with a line already in it: an empty private chat between two
    # people who have spoken once is a hard thing to start.
    chat_services.post_system_message(
        conversation, "حالا دوست هستید. گفتگو را همین‌جا ادامه دهید."
    )

    payload = {
        "conversation_id": str(conversation.id),
    }
    transaction.on_commit(
        lambda: (
            broadcast.to_users(
                [other.pk], "friend.accepted", {**payload, "user": _user_payload(user)}
            ),
            broadcast.to_users(
                [user.pk], "friend.accepted", {**payload, "user": _user_payload(other)}
            ),
        )
    )
    return row


@transaction.atomic
def decline_request(user: User, other_id: int) -> None:
    row = Friendship.objects.filter(
        from_user_id=other_id, to_user=user, status=FriendshipStatus.PENDING
    ).first()
    if row is None:
        raise DomainError("no_request", "درخواستی از این کاربر وجود ندارد.", 404)
    row.status = FriendshipStatus.DECLINED
    row.responded_at = timezone.now()
    row.save(update_fields=["status", "responded_at"])


@transaction.atomic
def remove(user: User, other_id: int) -> None:
    """Cancel a sent request, decline nothing, or unfriend — all one gesture.

    The client only knows "I no longer want this connection"; which of the
    three it is depends on state the server already has.
    """
    row = Friendship.objects.filter(
        Q(from_user=user, to_user_id=other_id) | Q(from_user_id=other_id, to_user=user)
    ).first()
    if row is None:
        return
    # The DIRECT conversation is deliberately left alone: the messages belong
    # to both people, and unfriending should not delete someone else's history.
    row.delete()
    logger.info(
        "social.removed",
        extra={"event": "social.removed", "user_id": user.pk, "target": other_id},
    )


def _user_payload(user: User) -> dict:
    return {
        "id": user.pk,
        "username": user.username,
        "display_name": user.display_name,
        "avatar": user.avatar,
    }
