"""Channel-layer fan-out.

Two group families, and the split matters:

  user.<id>   every conversation the person belongs to. Durable events go here,
              so a new message updates their chat list whether or not that
              conversation is on screen.
  conv.<uuid> only while the conversation's screen is open. Ephemeral traffic
              (typing, presence) that is never persisted and is worthless to
              someone who is not looking.

Sending durable events to the conversation group instead would mean a message
arriving while the user is on another screen never reaches their unread badge.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def user_group(user_id: int) -> str:
    return f"user.{user_id}"


def conversation_group(conversation_id) -> str:
    return f"conv.{conversation_id}"


def _send(group: str, event_type: str, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:  # pragma: no cover - only when channels is misconfigured
        return
    async_to_sync(layer.group_send)(
        group, {"type": "fanout", "event": event_type, "data": payload}
    )


def to_users(user_ids, event_type: str, payload: dict) -> None:
    for user_id in user_ids:
        _send(user_group(user_id), event_type, payload)


def to_conversation(conversation_id, event_type: str, payload: dict) -> None:
    _send(conversation_group(conversation_id), event_type, payload)
