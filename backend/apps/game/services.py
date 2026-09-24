"""The turn engine.

The server is the only authority on turn state. Clients never advance a turn
and never pick the next player — they render whatever snapshot they were last
handed.

**Nothing here runs on a clock.** A turn has no deadline. A room can sit on one
turn for an hour while the players talk about something else and then pick it
up again, which is how people actually use a chat. Advancement happens because
somebody says so:

    CHOOSING ──choose──▶ ANSWERING ──answer──▶ CONFIRMING ──confirm──▶ next
        │                     │                     │
        └──skip (own turn)────┴─────────────────────┴──▶ next
                              │
                     owner can force-advance from any of these

Who may confirm:

  * two players — the other one, and confirming makes it their turn
  * more players — more than half of everyone except the answerer
  * the room owner alone, at any point, answer or no answer

There is therefore always someone who can unstick a game: the owner. If they
leave, ownership passes to the longest-present player, so the button never
belongs to nobody.
"""

import logging
import random

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.chat import broadcast
from apps.chat import services as chat_services
from apps.chat.models import Conversation, ConversationType, MessageType
from apps.core.errors import DomainError
from apps.game.models import (
    GameSession,
    Prompt,
    PromptType,
    SessionStatus,
    Turn,
    TurnConfirmation,
    TurnStatus,
)
from apps.game.payloads import session_payload
from apps.users.models import User

logger = logging.getLogger("ft.game")

MIN_PLAYERS = 2


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def active_session(conversation_id) -> GameSession | None:
    return GameSession.objects.filter(
        conversation_id=conversation_id, status=SessionStatus.ACTIVE
    ).first()


def current_turn(session: GameSession) -> Turn | None:
    return (
        session.turns.select_related("prompt")
        .annotate(confirm_count=Count("confirmations"))
        .order_by("-index")
        .first()
    )


def confirmed_by(turn: Turn) -> list[int]:
    return list(turn.confirmations.values_list("user_id", flat=True))


def latest_session(conversation_id) -> GameSession | None:
    """The newest game in this conversation, running or finished.

    Distinct from `active_session`, which means "a game is in progress" and is
    what the rules check. This one is for display: a screen opened after a game
    ended still has to know that one ended, otherwise the app offers "start a
    game" to people who just finished one and the fact that they played at all
    disappears on the next reload.
    """
    return (
        GameSession.objects.filter(conversation_id=conversation_id)
        .order_by("-id")
        .first()
    )


def state_of(conversation_id) -> dict:
    session = latest_session(conversation_id)
    if session is None:
        return session_payload(None)

    # A finished game has no turn to act on; every open turn was closed when it
    # ended. Sending the last one would invite the UI to render a dead turn.
    if session.status != SessionStatus.ACTIVE:
        return session_payload(session, None)

    turn = current_turn(session)
    return session_payload(
        session,
        turn,
        confirmations=confirmed_by(turn) if turn else [],
        required=required_confirmations(session, turn) if turn else 0,
    )


def _require_turn(turn_id: int) -> Turn:
    turn = (
        Turn.objects.select_related("session", "session__conversation", "prompt")
        .filter(pk=turn_id)
        .first()
    )
    if turn is None:
        raise DomainError("turn_not_found", "نوبت پیدا نشد.", 404)
    return turn


def _require_own_turn(user: User, turn_id: int, expected: str) -> Turn:
    turn = _require_turn(turn_id)
    if turn.player_id != user.pk:
        raise DomainError("not_your_turn", "نوبت شما نیست.", 403)
    if turn.status != expected:
        raise DomainError("wrong_turn_state", "این کار در این مرحله ممکن نیست.", 409)
    return turn


def is_owner(user: User, conversation: Conversation) -> bool:
    """A DIRECT chat has two equals, so either of them counts as the owner."""
    if conversation.type == ConversationType.DIRECT:
        return True
    return conversation.owner_id == user.pk


def required_confirmations(session: GameSession, turn: Turn | None) -> int:
    """How many other players have to vouch before the turn moves on.

    Strictly more than half of everyone except the person whose turn it is —
    so with two players the other one decides alone, and with five the answerer
    needs three of the remaining four.
    """
    if turn is None:
        return 0
    others = [pid for pid in session.turn_order if pid != turn.player_id]
    if not others:
        return 0
    return len(others) // 2 + 1


# ---------------------------------------------------------------------------
# Broadcasting
# ---------------------------------------------------------------------------


def _publish(session: GameSession, turn: Turn | None) -> None:
    payload = session_payload(
        session,
        turn,
        confirmations=confirmed_by(turn) if turn else [],
        required=required_confirmations(session, turn) if turn else 0,
    )
    broadcast.to_users(
        chat_services.participant_user_ids(session.conversation_id),
        "game.state",
        payload,
    )


def _publish_later(session: GameSession) -> None:
    transaction.on_commit(lambda: _publish(session, current_turn(session)))


# ---------------------------------------------------------------------------
# Prompt selection
# ---------------------------------------------------------------------------


def _pick_prompt(session: GameSession, prompt_type: str) -> Prompt:
    queryset = Prompt.objects.filter(
        type=prompt_type,
        is_active=True,
        intensity__lte=session.max_intensity,
        min_players__lte=len(session.turn_order),
    )
    if session.category:
        queryset = queryset.filter(category=session.category)

    unused = queryset.exclude(pk__in=session.used_prompt_ids)
    # Running out mid-game is normal in a long session with a small bank;
    # recycling beats ending the game, and by then the repeats feel far apart.
    prompt = unused.order_by("?").first() or queryset.order_by("?").first()

    if prompt is None:
        raise DomainError("no_prompts", "سؤالی برای این تنظیمات پیدا نشد.", 503)

    if prompt.pk not in session.used_prompt_ids:
        session.used_prompt_ids = [*session.used_prompt_ids, prompt.pk]
        session.save(update_fields=["used_prompt_ids"])
    return prompt


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@transaction.atomic
def start_game(
    user: User,
    conversation: Conversation,
    *,
    category: str = "",
    max_intensity: int = 2,
) -> GameSession:
    """Start a game. Rooms are started by their owner; private chats by either.

    The game has no planned length. It keeps dealing turns around the table
    until somebody ends it — the same rule the room itself follows.

    A matched room no longer starts a game by itself. Two strangers dropped
    straight into a turn have to perform before they have said hello; letting
    them talk first and start when they want is the difference between a game
    and an interrogation.
    """
    chat_services.active_participant(user, conversation.id)

    if not is_owner(user, conversation):
        raise DomainError(
            "not_room_owner", "فقط سازنده‌ی روم می‌تواند بازی را شروع کند.", 403
        )

    if active_session(conversation.id):
        raise DomainError("game_running", "یک بازی در همین گفتگو در جریان است.", 409)

    player_ids = chat_services.participant_user_ids(conversation.id)
    if len(player_ids) < MIN_PLAYERS:
        raise DomainError(
            "not_enough_players", "برای شروع بازی حداقل دو نفر لازم است.", 409
        )

    random.shuffle(player_ids)

    session = GameSession.objects.create(
        conversation=conversation,
        turn_order=player_ids,
        category=category,
        max_intensity=max(1, min(3, max_intensity)),
        started_by=user,
    )

    logger.info(
        "game.started",
        extra={
            "event": "game.started",
            "session_id": session.pk,
            "conversation_id": str(conversation.id),
            "players": len(player_ids),
        },
    )

    # Everyone at the table gets the day, not just whoever pressed start.
    for player in User.objects.filter(pk__in=player_ids):
        player.record_play()

    chat_services.post_system_message(
        conversation, "بازی شروع شد!", meta={"game": "started", "session_id": session.pk}
    )
    _open_turn(session)
    return session


def _open_turn(session: GameSession) -> Turn:
    player_id = session.turn_order[session.turn_index % len(session.turn_order)]
    turn = Turn.objects.create(
        session=session,
        player_id=player_id,
        index=session.turn_index,
        status=TurnStatus.CHOOSING,
    )
    transaction.on_commit(lambda: _publish(session, turn))
    return turn


@transaction.atomic
def choose(user: User, turn_id: int, choice: str) -> Turn:
    turn = _require_own_turn(user, turn_id, TurnStatus.CHOOSING)

    if choice not in (PromptType.TRUTH, PromptType.DARE):
        raise DomainError("bad_choice", "انتخاب نامعتبر است.")

    session = turn.session
    prompt = _pick_prompt(session, choice)

    turn.choice = choice
    turn.prompt = prompt
    turn.status = TurnStatus.ANSWERING
    turn.version += 1
    turn.save(update_fields=["choice", "prompt", "status", "version"])

    # The prompt is a message, so it sits in the same scroll as the replies it
    # provokes rather than in a separate panel beside them.
    chat_services.post_message(
        conversation=session.conversation,
        sender=None,
        body=prompt.text,
        message_type=MessageType.GAME_PROMPT,
        meta={
            "turn_id": turn.pk,
            "player_id": turn.player_id,
            "choice": choice,
            "intensity": prompt.intensity,
        },
    )

    transaction.on_commit(lambda: _publish(session, turn))
    return turn


@transaction.atomic
def answer(user: User, turn_id: int, body: str) -> Turn:
    turn = _require_own_turn(user, turn_id, TurnStatus.ANSWERING)

    body = (body or "").strip()
    if not body:
        raise DomainError("empty_answer", "پاسخ خالی است.")

    session = turn.session
    message, _ = chat_services.post_message(
        conversation=session.conversation,
        sender=user,
        body=body,
        message_type=MessageType.GAME_ANSWER,
        meta={"turn_id": turn.pk, "choice": turn.choice},
    )

    turn.answer_message = message
    turn.status = TurnStatus.CONFIRMING
    turn.version += 1
    turn.save(update_fields=["answer_message", "status", "version"])

    logger.info(
        "game.answered",
        extra={"event": "game.answered", "session_id": session.pk, "turn_id": turn.pk},
    )

    transaction.on_commit(lambda: _publish(session, turn))
    return turn


@transaction.atomic
def confirm(user: User, turn_id: int) -> Turn:
    """Vouch that the player did what was asked.

    The owner's word is enough on its own; anyone else counts towards the
    majority. The answerer cannot confirm their own turn, which is the only
    rule here that needs stating.
    """
    turn = _require_turn(turn_id)
    session = turn.session

    if turn.status != TurnStatus.CONFIRMING:
        raise DomainError("wrong_turn_state", "این کار در این مرحله ممکن نیست.", 409)
    if turn.player_id == user.pk:
        raise DomainError("cannot_confirm_own", "نوبت خودتان را نمی‌توانید تأیید کنید.", 403)

    chat_services.active_participant(user, session.conversation_id)
    TurnConfirmation.objects.get_or_create(turn=turn, user=user)

    owner_decided = is_owner(user, session.conversation)
    enough = turn.confirmations.count() >= required_confirmations(session, turn)

    if owner_decided or enough:
        _close_turn(turn, TurnStatus.DONE)
    else:
        transaction.on_commit(lambda: _publish(session, turn))

    return turn


@transaction.atomic
def skip(user: User, turn_id: int) -> Turn:
    """The player gives up their own turn. Nobody else has to agree."""
    turn = _require_turn(turn_id)
    if turn.player_id != user.pk:
        raise DomainError("not_your_turn", "نوبت شما نیست.", 403)
    if turn.status not in (TurnStatus.CHOOSING, TurnStatus.ANSWERING):
        raise DomainError("wrong_turn_state", "این کار در این مرحله ممکن نیست.", 409)

    return _close_turn(turn, TurnStatus.SKIPPED, "رد کرد.")


@transaction.atomic
def force_next(user: User, turn_id: int) -> Turn:
    """The owner moves the game on regardless of what the turn is waiting for.

    This is the valve that replaces the timers. Someone stopped replying, or
    the room simply wants to move — with no clock to do it, a person has to,
    and it is the owner.
    """
    turn = _require_turn(turn_id)
    session = turn.session

    if not is_owner(user, session.conversation):
        raise DomainError("not_room_owner", "فقط سازنده‌ی روم می‌تواند نوبت را رد کند.", 403)
    if not turn.is_open:
        raise DomainError("wrong_turn_state", "این نوبت بسته شده است.", 409)

    answered = turn.answer_message_id is not None
    return _close_turn(
        turn,
        TurnStatus.DONE if answered else TurnStatus.SKIPPED,
        "" if answered else "رد شد.",
    )


def _close_turn(turn: Turn, status: str, verb: str = "") -> Turn:
    turn.status = status
    turn.version += 1
    turn.save(update_fields=["status", "version"])

    if verb:
        name = turn.player.display_name or turn.player.username
        chat_services.post_system_message(
            turn.session.conversation,
            f"نوبت {name} {verb}",
            meta={"turn_id": turn.pk, "game": "skipped"},
        )

    _advance(turn.session)
    return turn


def _advance(session: GameSession) -> Turn | None:
    """Open the next turn. There is no finish line.

    A game used to stop once everyone had taken their rounds, which meant the
    software decided when people were done talking. Now the only things that
    end a game are somebody ending it and the room emptying out below two
    players — the same shape as every other rule here, where nothing expires
    on its own and no clock overrules the people playing.
    """
    session.turn_index += 1
    session.save(update_fields=["turn_index"])

    if len(session.turn_order) < MIN_PLAYERS:
        end_game(session, "not_enough_players")
        return None

    return _open_turn(session)


@transaction.atomic
def end_game(session: GameSession, reason: str) -> None:
    if session.status == SessionStatus.ENDED:
        return

    session.status = SessionStatus.ENDED
    session.ended_at = timezone.now()
    session.ended_reason = reason
    session.save(update_fields=["status", "ended_at", "ended_reason"])

    Turn.objects.filter(
        session=session,
        status__in=(TurnStatus.CHOOSING, TurnStatus.ANSWERING, TurnStatus.CONFIRMING),
    ).update(status=TurnStatus.DONE)

    logger.info(
        "game.ended",
        extra={"event": "game.ended", "session_id": session.pk, "reason": reason},
    )

    # There is no "completed" any more — a game only ends because somebody
    # ended it or because the room ran out of players, and the line in the
    # chat should say which.
    notice = {
        "stopped": "بازی تمام شد.",
        "not_enough_players": "بازی متوقف شد — نفر کافی نمانده.",
    }.get(reason, "بازی متوقف شد.")

    chat_services.post_system_message(
        session.conversation,
        notice,
        meta={"game": "ended", "reason": reason},
    )
    transaction.on_commit(lambda: _publish(session, None))


@transaction.atomic
def stop_game(user: User, conversation_id) -> None:
    participant = chat_services.active_participant(user, conversation_id)
    session = active_session(conversation_id)
    if session is None:
        raise DomainError("no_game", "بازی فعالی وجود ندارد.", 404)
    if not is_owner(user, participant.conversation):
        raise DomainError("not_room_owner", "فقط سازنده‌ی روم می‌تواند بازی را متوقف کند.", 403)
    end_game(session, "stopped")


# ---------------------------------------------------------------------------
# Departures
# ---------------------------------------------------------------------------


@transaction.atomic
def on_participant_left(conversation_id, user_id: int) -> None:
    """A player leaving is a defined transition, not an exception.

    With no deadlines, a player who walks out mid-turn would otherwise stall
    the game indefinitely — so their turn closes immediately. Their departure
    also lowers the confirmation threshold, which can be enough to release a
    turn that was already waiting.
    """
    session = active_session(conversation_id)
    if session is None or user_id not in session.turn_order:
        return

    session.turn_order = [pid for pid in session.turn_order if pid != user_id]
    session.save(update_fields=["turn_order"])

    if len(session.turn_order) < MIN_PLAYERS:
        end_game(session, "not_enough_players")
        return

    turn = current_turn(session)
    if turn is None or not turn.is_open:
        _publish_later(session)
        return

    if turn.player_id == user_id:
        _close_turn(turn, TurnStatus.SKIPPED, "ترک کرد.")
        return

    # Someone who had already confirmed may have left, or the threshold may
    # simply have dropped below what is already recorded.
    TurnConfirmation.objects.filter(turn=turn, user_id=user_id).delete()
    if (
        turn.status == TurnStatus.CONFIRMING
        and turn.confirmations.count() >= required_confirmations(session, turn)
    ):
        _close_turn(turn, TurnStatus.DONE)
    else:
        _publish_later(session)
