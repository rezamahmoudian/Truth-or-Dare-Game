"""Wire format for game state.

The client is sent a complete snapshot on every transition rather than a stream
of deltas. Deltas require the client to run its own copy of the state machine
and to receive every event in order — neither of which survives a dropped
socket on mobile data. A snapshot is idempotent: applying it twice, or applying
only the latest one after a reconnect, gives the right screen either way.
"""

from apps.game.models import GameSession, Turn
from apps.users.models import User


def prompt_payload(prompt) -> dict | None:
    if prompt is None:
        return None
    return {
        "id": prompt.pk,
        "type": prompt.type,
        "text": prompt.text,
        "category": prompt.category,
        "intensity": prompt.intensity,
    }


def turn_payload(
    turn: Turn | None,
    *,
    confirmations: list[int] | None = None,
    required: int = 0,
) -> dict | None:
    if turn is None:
        return None
    return {
        "id": turn.pk,
        "index": turn.index,
        "player_id": turn.player_id,
        "status": turn.status,
        "choice": turn.choice,
        "prompt": prompt_payload(turn.prompt),
        "answer_message_id": turn.answer_message_id,
        # Who has vouched so far and how many are needed. The client shows
        # "۱ از ۲" rather than a bare button, so waiting has a visible reason.
        "confirmations": confirmations or [],
        "confirmations_required": required,
        "version": turn.version,
    }


def session_payload(
    session: GameSession | None,
    turn: Turn | None = None,
    *,
    confirmations: list[int] | None = None,
    required: int = 0,
) -> dict:
    if session is None:
        return {"session": None, "turn": None}

    return {
        "session": {
            "id": session.pk,
            "conversation_id": str(session.conversation_id),
            "status": session.status,
            "turn_order": session.turn_order,
            "turn_index": session.turn_index,
            "total_turns": session.total_turns,
            "rounds": session.rounds,
            "category": session.category,
            "max_intensity": session.max_intensity,
            "ended_reason": session.ended_reason,
        },
        "turn": turn_payload(turn, confirmations=confirmations, required=required),
    }


def player_payload(user: User) -> dict:
    return {
        "id": user.pk,
        "display_name": user.display_name,
        "avatar": user.avatar,
    }
