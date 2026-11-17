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
        "vip": user.vip,
        "id": user.pk,
        "username": user.username,
        "display_name": user.display_name,
        "avatar": user.avatar,
        "avatar_url": user.avatar_url,
        "is_ai": user.is_ai,
    }


def message_payload(message: Message, viewer: User | None = None) -> dict:
    reactions: defaultdict[str, list[int]] = defaultdict(list)
    # This is a query unless the caller prefetched `reactions` — history does,
    # and `post_message` primes an empty cache for the message it just wrote.
    for reaction in message.reactions.all():
        reactions[reaction.emoji].append(reaction.user_id)

    meta = dict(message.meta or {})
    if message.type == "GAME_PROMPT":
        # Keep the question card self-contained in both history and socket
        # payloads.  Counts are prompt-wide; `user_value` is private to the
        # viewer and is only filled for history requests.
        try:
            prompt_id = int(meta.get("prompt_id"))
        except (TypeError, ValueError):
            prompt_id = 0
        if not prompt_id:
            # Prompt messages created before feedback was introduced only had
            # the turn id.  Resolve that legacy shape so old chat history can
            # still receive votes.
            try:
                turn_id = int(meta.get("turn_id"))
            except (TypeError, ValueError):
                turn_id = 0
            if turn_id:
                from apps.game.models import Turn
                prompt_id = Turn.objects.filter(pk=turn_id).values_list("prompt_id", flat=True).first() or 0
        if prompt_id:
            from apps.game.models import PromptFeedback, PromptFeedbackValue
            from django.db.models import Count, Q

            totals = PromptFeedback.objects.filter(prompt_id=prompt_id).aggregate(
                positive=Count("id", filter=Q(value=PromptFeedbackValue.POSITIVE)),
                negative=Count("id", filter=Q(value=PromptFeedbackValue.NEGATIVE)),
            )
            current = None
            if viewer is not None:
                current = (
                    PromptFeedback.objects.filter(prompt_id=prompt_id, user=viewer)
                    .values_list("value", flat=True)
                    .first()
                )
            meta["feedback"] = {
                "positive_count": totals["positive"] or 0,
                "negative_count": totals["negative"] or 0,
                "user_value": current,
            }

    return {
        "id": message.pk,
        "conversation_id": str(message.conversation_id),
        "type": message.type,
        "body": "" if message.is_deleted else message.body,
        "attachment": (
            {**message.attachment_info, "url": f"/conversations/{message.conversation_id}/messages/{message.pk}/attachment/"}
            if message.attachment and not message.is_deleted else None
        ),
        "sender": user_payload(message.sender),
        "reply_to_id": message.reply_to_id,
        "client_id": message.client_id,
        "meta": meta,
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
    from apps.billing.vip import hydrate
    participants = hydrate(participants or [])
    return {
        "id": str(conversation.id),
        "type": conversation.type,
        "status": conversation.status,
        "code": conversation.code,
        "owner_id": conversation.owner_id,
        "max_players": conversation.max_players,
        "is_system": conversation.is_system,
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
