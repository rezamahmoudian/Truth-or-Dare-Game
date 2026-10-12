"""Persistent game invitations. A room exists only after the recipient accepts."""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.chat import broadcast, presence
from apps.chat import services as chat
from apps.chat.models import Participant
from apps.core.errors import DomainError
from apps.game import services as game
from apps.matchmaking.models import MatchTicket, TicketState
from apps.users.models import GameInvitation, User
from apps.users.payloads import person_payload
from apps.users.social import _resolve


def payload(row, viewer_id):
    return {"id": row.pk, "direction": "outgoing" if row.from_user_id == viewer_id else "incoming",
            "user": person_payload(row.to_user if row.from_user_id == viewer_id else row.from_user),
            "status": row.status, "created_at": row.created_at.isoformat(),
            "conversation_id": str(row.conversation_id) if row.conversation_id else None}


def _notify(row):
    for viewer_id in (row.from_user_id, row.to_user_id):
        data = payload(row, viewer_id)
        transaction.on_commit(lambda uid=viewer_id, data=data: broadcast.to_users([uid], "game.invitation", data))


def lists(user):
    blocked = set(user.blocks_made.values_list("blocked_id", flat=True)) | set(user.blocks_received.values_list("blocker_id", flat=True))
    rows = GameInvitation.objects.filter(Q(from_user=user) | Q(to_user=user)).filter(
        Q(status="PENDING") | Q(status="ACCEPTED", conversation__status="ACTIVE")
    ).exclude(from_user_id__in=blocked).exclude(to_user_id__in=blocked).filter(
        from_user__is_active=True, to_user__is_active=True
    ).select_related("from_user", "to_user", "conversation").order_by("-created_at")
    result = {"incoming": [], "outgoing": [], "ready": []}
    ready_conversations = set()
    for row in rows:
        if row.status == "ACCEPTED":
            if not Participant.objects.filter(conversation_id=row.conversation_id, user=user, left_at__isnull=True).exists():
                continue
            if row.conversation_id in ready_conversations:
                continue
            ready_conversations.add(row.conversation_id)
            key = "ready"
        else:
            key = "outgoing" if row.from_user_id == user.pk else "incoming"
        result[key].append(payload(row, user.pk))
    return result


def _eligible(user):
    if not user.is_active or user.is_ai or not user.is_onboarded or user.age is None or user.age < 18:
        raise DomainError("game_invite_not_allowed", "برای دعوت به بازی، پروفایل بزرگسال باید کامل باشد.", 403)


@transaction.atomic
def send(user, other_id):
    other = _resolve(user, other_id)
    # A stable pair lock also serializes simultaneous invitations in opposite directions.
    list(User.objects.select_for_update().filter(pk__in=[user.pk, other.pk]).order_by("pk"))
    _eligible(user)
    _eligible(other)
    existing = GameInvitation.objects.filter(
        Q(from_user=user, to_user=other) | Q(from_user=other, to_user=user), status="PENDING"
    ).select_related("from_user", "to_user").first()
    if existing:
        return existing
    if other.pk not in presence.app_online_ids():
        raise DomainError("user_offline", "این بازیکن اکنون آنلاین نیست؛ کمی بعد دوباره امتحان کن.", 409)
    if GameInvitation.objects.filter(from_user=user, status="PENDING").count() >= 10:
        raise DomainError("invite_limit", "ابتدا منتظر پاسخ دعوت‌های قبلی بمان یا آن‌ها را لغو کن.", 429)
    row = GameInvitation.objects.create(from_user=user, to_user=other)
    _notify(row)
    return row


@transaction.atomic
def respond(user, invitation_id, action, *, conversation_id=None):
    row = GameInvitation.objects.select_for_update(of=("self",)).select_related("from_user", "to_user").filter(
        Q(from_user=user) | Q(to_user=user), pk=invitation_id).first()
    if row is None:
        raise DomainError("invitation_not_found", "دعوت پیدا نشد.", 404)
    if action not in ("accept", "decline", "cancel"):
        raise DomainError("invalid_action", "عملیات نامعتبر است.")
    if (action == "cancel" and user.pk != row.from_user_id) or (action != "cancel" and user.pk != row.to_user_id):
        raise DomainError("invitation_forbidden", "اجازهٔ انجام این کار را نداری.", 403)
    if row.status != "PENDING":
        if action == "accept" and row.status == "ACCEPTED":
            _resolve(user, row.from_user_id)
            return row
        if row.status == {"decline": "DECLINED", "cancel": "CANCELLED"}.get(action):
            return row
        raise DomainError("invitation_resolved", "این دعوت قبلاً تعیین تکلیف شده است.", 409)
    if action == "accept":
        _resolve(user, row.from_user_id)
        _eligible(row.from_user)
        _eligible(row.to_user)
        ids = [row.from_user_id, row.to_user_id]
        # Stop random matchmaking before creating the accepted invitation's room.
        tickets = list(MatchTicket.objects.select_for_update().filter(user_id__in=ids, state=TicketState.QUEUED).order_by("pk"))
        for ticket in tickets:
            ticket.state = TicketState.CANCELLED
            ticket.save(update_fields=["state"])
            transaction.on_commit(lambda uid=ticket.user_id: broadcast.to_users([uid], "mm.cancelled", {}))
        room = chat.get_or_create_pair(row.from_user, row.to_user, room=True, preferred_id=conversation_id)
        chat.post_system_message(room, "دعوت بازی پذیرفته شد. بازی دونفره آماده است!")
        if not game.active_session(room.pk):
            # Both participants agreed; an existing ROOM may belong to the recipient.
            game.start_game(room.owner if room.type == "ROOM" else row.from_user, room)
        row.conversation = room
        row.status = "ACCEPTED"
    else:
        row.status = "DECLINED" if action == "decline" else "CANCELLED"
    row.responded_at = timezone.now()
    row.save(update_fields=["status", "responded_at", "conversation"])
    _notify(row)
    return row
