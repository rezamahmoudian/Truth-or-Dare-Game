"""Reporting, blocking and message removal."""

import logging

from django.db import IntegrityError, transaction

from apps.chat.models import ConversationType, Message
from apps.core.errors import DomainError
from apps.users.models import Block, Friendship, Report, ReportReason, User

logger = logging.getLogger("ft.moderation")


def _resolve(user: User, other_id: int) -> User:
    other = User.objects.filter(pk=other_id).first()
    if other is None:
        raise DomainError("user_not_found", "کاربر پیدا نشد.", 404)
    if other.pk == user.pk:
        raise DomainError("self_action", "این کار روی خودتان ممکن نیست.", 400)
    return other


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report(
    reporter: User,
    target_user_id: int,
    reason: str,
    *,
    note: str = "",
    message_id: int | None = None,
) -> Report:
    """File a report against a user, optionally about one message.

    Reports are never auto-actioned. An automatic ban on N reports is a weapon
    handed to anyone who can organise three friends; a human reads these.
    """
    target = _resolve(reporter, target_user_id)

    if reason not in ReportReason.values:
        raise DomainError("bad_reason", "دلیل گزارش نامعتبر است.")

    message = None
    if message_id is not None:
        message = Message.objects.filter(pk=message_id).first()
        if message is None:
            raise DomainError("message_not_found", "پیام پیدا نشد.", 404)
        # Only about a conversation the reporter was actually in, so a report
        # cannot be used to fish for other people's messages by id.
        from apps.chat import services as chat_services

        chat_services.active_participant(reporter, message.conversation_id)

    row = Report.objects.create(
        reporter=reporter,
        target_user=target,
        target_message=message,
        reason=reason,
        note=note[:500],
    )

    logger.warning(
        "moderation.report_filed",
        extra={
            "event": "moderation.report_filed",
            "report_id": row.pk,
            "reporter_id": reporter.pk,
            "target_id": target.pk,
            "reason": reason,
        },
    )
    return row


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------


@transaction.atomic
def block(user: User, other_id: int) -> Block:
    """Block someone, and undo whatever connection already existed.

    Blocking has to remove the friendship too. Leaving it in place would keep
    the other person in your friends list and keep the private conversation
    live from their side, which is not what anyone means by "block".
    """
    other = _resolve(user, other_id)

    try:
        row = Block.objects.create(blocker=user, blocked=other)
    except IntegrityError:
        existing = Block.objects.filter(blocker=user, blocked=other).first()
        if existing is None:
            raise
        return existing

    Friendship.objects.filter(from_user=user, to_user=other).delete()
    Friendship.objects.filter(from_user=other, to_user=user).delete()

    logger.info(
        "moderation.blocked",
        extra={"event": "moderation.blocked", "user_id": user.pk, "target": other.pk},
    )
    return row


def unblock(user: User, other_id: int) -> None:
    Block.objects.filter(blocker=user, blocked_id=other_id).delete()


def blocked_users(user: User) -> list[User]:
    return [
        row.blocked
        for row in Block.objects.filter(blocker=user).select_related("blocked")
    ]


def assert_not_blocked(sender: User, conversation) -> None:
    """Refuse a private message between two people where one blocked the other.

    Only meaningful for DIRECT conversations: a room is a shared space and
    blocking there is handled by never matching the pair in the first place.
    """
    if conversation.type != ConversationType.DIRECT:
        return

    from apps.chat import services as chat_services

    for other in chat_services.participants_of(conversation.id):
        if other.pk != sender.pk and sender.blocks_or_blocked_by(other):
            raise DomainError(
                "blocked", "امکان ارسال پیام به این کاربر وجود ندارد.", 403
            )


# ---------------------------------------------------------------------------
# Message removal
# ---------------------------------------------------------------------------


def delete_message(user: User, message_id: int) -> Message:
    """Soft-delete a message. Authors may remove their own; staff, any.

    Soft rather than hard: a report may point at this message, and a moderator
    reading it tomorrow needs to see what was actually said.
    """
    message = Message.objects.filter(pk=message_id).select_related(
        "conversation"
    ).first()
    if message is None:
        raise DomainError("message_not_found", "پیام پیدا نشد.", 404)

    if message.sender_id != user.pk and not user.is_staff:
        raise DomainError("not_your_message", "فقط فرستنده می‌تواند پیام را حذف کند.", 403)

    if message.is_deleted:
        return message

    message.is_deleted = True
    message.save(update_fields=["is_deleted"])

    from apps.chat import broadcast
    from apps.chat import services as chat_services
    from apps.chat.payloads import message_payload

    broadcast.to_users(
        chat_services.participant_user_ids(message.conversation_id),
        "chat.message",
        message_payload(message),
    )
    return message
