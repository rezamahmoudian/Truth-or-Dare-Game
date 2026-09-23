"""Wire formats.

Plain dict builders rather than DRF serializers, used by both the REST views
and the WebSocket consumer. The point is that a message fetched from history
and a message pushed over the socket are byte-for-byte the same shape — if the
two paths had separate serializers they would drift, and the client would need
to handle both.
"""

from collections import defaultdict

from apps.chat.models import Conversation, Message
from apps.users.models import User


def user_payload(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.pk,
        "username": user.username,
        "display_name": user.display_name,
        "avatar": user.avatar,
    }


def message_payload(message: Message) -> dict:
    reactions: defaultdict[str, list[int]] = defaultdict(list)
    # Only touches the DB when reactions were prefetched or already loaded.
    for reaction in message.reactions.all():
        reactions[reaction.emoji].append(reaction.user_id)

    return {
        "id": message.pk,
        "conversation_id": str(message.conversation_id),
        "type": message.type,
        "body": "" if message.is_deleted else message.body,
        "sender": user_payload(message.sender),
        "reply_to_id": message.reply_to_id,
        "client_id": message.client_id,
        "meta": message.meta,
        "created_at": message.created_at.isoformat(),
        "is_deleted": message.is_deleted,
        "reactions": dict(reactions),
    }


def conversation_payload(
    conversation: Conversation,
    *,
    unread_count: int = 0,
    participants: list[User] | None = None,
) -> dict:
    return {
        "id": str(conversation.id),
        "type": conversation.type,
        "status": conversation.status,
        "code": conversation.code,
        "owner_id": conversation.owner_id,
        "max_players": conversation.max_players,
        "created_at": conversation.created_at.isoformat(),
        "last_message_at": (
            conversation.last_message_at.isoformat()
            if conversation.last_message_at
            else None
        ),
        "last_message_preview": conversation.last_message_preview,
        "unread_count": unread_count,
        "participants": [user_payload(u) for u in (participants or [])],
    }
