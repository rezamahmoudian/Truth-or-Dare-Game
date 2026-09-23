"""End-to-end exercise of the turn engine.

The engine has no clock. A turn waits for a person, and the only ways past it
are the player acting, other players confirming, or the room owner deciding.
So this suite is mostly about *who is allowed to move the game on*:

  * the owner starts it — a matched room no longer starts one by itself
  * two players: the other one confirms, and it becomes their turn
  * more players: more than half of everyone except the answerer
  * the owner alone, at any moment, answered or not

And about what must not happen: no turn advances because time passed, and
nobody confirms their own turn.
"""

import asyncio
import contextlib
import json
import os
import pathlib
import secrets
import sys
import time
import urllib.error
import urllib.request

import django
import websockets

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.chat.models import Conversation  # noqa: E402
from apps.game.models import GameSession, Turn, TurnStatus  # noqa: E402

BASE = "http://localhost:8000/api"
WS = "ws://localhost:8000/ws/"
ORIGIN = "http://localhost:8000"

results: list[tuple[str, bool, str]] = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def http(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        return err.code, (json.loads(raw) if raw else None)


def wait_ready(timeout=30.0):
    """Block until the API answers, so an edit-triggered reload is not a red run."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.suppress(Exception):
            status, _ = http("GET", "/health/")
            if status == 200:
                return
        time.sleep(0.5)
    raise SystemExit("API did not become ready")


def new_user(name, gender, birth="1995-05-05"):
    _, data = http("POST", "/auth/guest/", body={"device_token": secrets.token_hex(24)})
    token = data["access"]
    http("PATCH", "/users/me/", token,
         {"display_name": name, "gender": gender, "birth_date": birth, "avatar": "a4"})
    return token, data["user"]["id"]


class Player:
    def __init__(self, name, token, user_id):
        self.name, self.token, self.id = name, token, user_id
        self.states: list[dict] = []

    async def connect(self, conversation_id):
        self.ws = await websockets.connect(
            WS, subprotocols=["ft.jwt", self.token], origin=ORIGIN
        )
        await self.ws.recv()
        await self.send("conv.subscribe", {"conversation_id": conversation_id})
        self._pump = asyncio.create_task(self._read())

    async def _read(self):
        with contextlib.suppress(Exception):
            async for raw in self.ws:
                frame = json.loads(raw)
                if frame["type"] in ("game.state", "error"):
                    self.states.append(frame)

    async def send(self, action, data):
        await self.ws.send(json.dumps({"type": action, "data": data}))

    def last_state(self):
        for frame in reversed(self.states):
            if frame["type"] == "game.state":
                return frame["data"]
        return None

    def last_error(self):
        for frame in reversed(self.states):
            if frame["type"] == "error":
                return frame["data"]
        return None

    async def close(self):
        self._pump.cancel()
        await self.ws.close()


async def db(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


async def wait_for(predicate, timeout=8.0, interval=0.05):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(interval)
    return None


async def wait_turn(player, matches, timeout=8.0):
    return await wait_for(
        lambda: (lambda st: st if st and st.get("turn") and matches(st["turn"]) else None)(
            player.last_state()
        ),
        timeout,
    )


async def wait_error(player, code, timeout=8.0):
    return await wait_for(
        lambda: (lambda e: e if e and e.get("code") == code else None)(player.last_error()),
        timeout,
    )


def turn_row(turn_id):
    return Turn.objects.select_related("prompt", "player").get(pk=turn_id)


def load_session(session_id):
    return GameSession.objects.get(pk=session_id)


async def two_player_game():
    """The common case: the other player confirms, and the turn passes to them."""
    a = Player("آیدا", *new_user("آیدا", "F"))
    b = Player("بهرام", *new_user("بهرام", "M"))

    _, room = http("POST", "/conversations/rooms/", a.token, {"max_players": 4})
    conv_id, code = room["id"], room["code"]
    http("POST", "/conversations/join/", b.token, {"code": code})
    check("the room owner is whoever opened it", room["owner_id"] == a.id,
          str(room["owner_id"]))

    for player in (a, b):
        await player.connect(conv_id)

    # --- nothing starts on its own ----------------------------------------
    _, state = http("GET", f"/conversations/{conv_id}/game/", a.token)
    check("a room does not start a game by itself", state["session"] is None)

    status, _ = http("POST", f"/conversations/{conv_id}/game/", b.token, {"rounds": 2})
    check("only the owner can start it", status == 403, str(status))

    status, started = http("POST", f"/conversations/{conv_id}/game/", a.token,
                           {"rounds": 2})
    check("the owner starts it", status == 201 and started["session"]["status"] == "ACTIVE")

    turn = started["turn"]
    check("the first turn is open", turn["status"] == "CHOOSING")
    check("a turn carries no deadline", "deadline_at" not in turn)

    by_id = {a.id: a, b.id: b}
    current = by_id[turn["player_id"]]
    other = b if current is a else a

    # --- choose and answer -------------------------------------------------
    await current.send("game.choose", {"turn_id": turn["id"], "choice": "TRUTH"})
    state = await wait_turn(current, lambda t: t["status"] == "ANSWERING")
    check("choosing serves a prompt", bool(state) and bool(state["turn"]["prompt"]),
          (state["turn"]["prompt"] or {}).get("text", "")[:40] if state else "")

    await current.send("game.answer", {"turn_id": turn["id"], "body": "جوابم اینه!"})
    state = await wait_turn(current, lambda t: t["status"] == "CONFIRMING")
    check("answering waits for confirmation, not a timer", bool(state))
    check("with two players one confirmation is needed",
          state["turn"]["confirmations_required"] == 1,
          str(state["turn"]["confirmations_required"]) if state else "")

    # --- nothing moves on its own ------------------------------------------
    await asyncio.sleep(3)
    row = await db(turn_row, turn["id"])
    check("three seconds of silence changes nothing",
          row.status == TurnStatus.CONFIRMING, row.status)

    await current.send("game.confirm", {"turn_id": turn["id"]})
    check("you cannot confirm your own turn",
          bool(await wait_error(current, "cannot_confirm_own")))

    # --- the other player confirms -----------------------------------------
    await other.send("game.confirm", {"turn_id": turn["id"]})
    state = await wait_turn(other, lambda t: t["index"] == 1)
    check("confirming moves the game on", bool(state))
    check("and it becomes the confirmer's turn",
          bool(state) and state["turn"]["player_id"] == other.id,
          str(state["turn"]["player_id"]) if state else "")

    # --- the owner can force it --------------------------------------------
    second = state["turn"]
    await a.send("game.force_next", {"turn_id": second["id"]})
    forced = await wait_turn(a, lambda t: t["index"] == 2)
    check("the owner can move on with no answer at all", bool(forced))
    row = await db(turn_row, second["id"])
    check("a forced turn with no answer counts as skipped",
          row.status == TurnStatus.SKIPPED, row.status)

    third = forced["turn"]
    await b.send("game.force_next", {"turn_id": third["id"]})
    check("a non-owner cannot force the game on",
          bool(await wait_error(b, "not_room_owner")))

    for player in (a, b):
        await player.close()


async def group_game():
    """Four players: a majority of the others has to agree."""
    players = [
        Player(f"گروهی {i}", *new_user(f"گروهی {i}", "M" if i % 2 else "F"))
        for i in range(4)
    ]
    owner = players[0]

    _, room = http("POST", "/conversations/rooms/", owner.token, {"max_players": 8})
    conv_id = room["id"]
    for player in players[1:]:
        http("POST", "/conversations/join/", player.token, {"code": room["code"]})
    for player in players:
        await player.connect(conv_id)

    _, started = http("POST", f"/conversations/{conv_id}/game/", owner.token,
                      {"rounds": 1})
    turn = started["turn"]
    by_id = {p.id: p for p in players}
    current = by_id[turn["player_id"]]
    others = [p for p in players if p is not current]

    await current.send("game.choose", {"turn_id": turn["id"], "choice": "DARE"})
    await wait_turn(current, lambda t: t["status"] == "ANSWERING")
    await current.send("game.answer", {"turn_id": turn["id"], "body": "انجام دادم"})
    state = await wait_turn(current, lambda t: t["status"] == "CONFIRMING")

    check("with four players two of the other three must agree",
          state["turn"]["confirmations_required"] == 2,
          str(state["turn"]["confirmations_required"]) if state else "")

    # One vote is not enough — unless it is the owner's.
    voter = next(p for p in others if p is not owner)
    await voter.send("game.confirm", {"turn_id": turn["id"]})
    counted = await wait_turn(current, lambda t: len(t["confirmations"]) == 1)
    check("a single vote is recorded but does not advance", bool(counted))
    row = await db(turn_row, turn["id"])
    check("the turn is still waiting", row.status == TurnStatus.CONFIRMING, row.status)

    second_voter = next(p for p in others if p not in (owner, voter))
    await second_voter.send("game.confirm", {"turn_id": turn["id"]})
    moved = await wait_turn(current, lambda t: t["index"] == 1)
    check("a majority of the others advances it", bool(moved))

    # The owner's single vote on someone else's turn.
    next_turn = moved["turn"]
    next_player = by_id[next_turn["player_id"]]
    await next_player.send("game.choose", {"turn_id": next_turn["id"], "choice": "TRUTH"})
    await wait_turn(next_player, lambda t: t["status"] == "ANSWERING")
    await next_player.send("game.answer", {"turn_id": next_turn["id"], "body": "بله"})
    await wait_turn(next_player, lambda t: t["status"] == "CONFIRMING")

    # Deciders are relative to *this* turn's player, not the previous one.
    if next_player is owner:
        # The owner answering has no special power over their own turn: the
        # ordinary majority applies.
        voters = [p for p in players if p is not owner][:2]
        for voter_ in voters:
            await voter_.send("game.confirm", {"turn_id": next_turn["id"]})
        advanced = await wait_turn(owner, lambda t: t["index"] == 2)
        check("the owner's own turn still needs the usual majority", bool(advanced))
    else:
        await owner.send("game.confirm", {"turn_id": next_turn["id"]})
        advanced = await wait_turn(owner, lambda t: t["index"] == 2)
        check("the owner's word alone is enough on someone else's turn",
              bool(advanced))

    # --- someone walks out mid-game ----------------------------------------
    session_id = started["session"]["id"]
    leaver = next(p for p in players if p is not owner)
    http("POST", f"/conversations/{conv_id}/leave/", leaver.token)
    session = await wait_for(
        lambda: True, timeout=0.3
    )
    session = await db(load_session, session_id)
    check("a player who leaves is dropped from the order",
          leaver.id not in session.turn_order, str(session.turn_order))
    check("and the game carries on for the rest",
          session.status == "ACTIVE", session.status)

    for player in players:
        with contextlib.suppress(Exception):
            await player.close()


async def matched_rooms_do_not_autostart():
    from apps.matchmaking import services as mm

    a_token, a_id = new_user("صف ۱", "F")
    b_token, b_id = new_user("صف ۲", "M")
    http("POST", "/match/", a_token, {"mode": "quick"})
    http("POST", "/match/", b_token, {"mode": "quick"})
    await db(mm.run_matcher)
    await db(mm.run_matcher)

    _, chats = http("GET", "/conversations/", a_token)
    room = next((c for c in chats if c["type"] == "ROOM"), None)
    check("matchmaking still produces a room", room is not None)

    if room:
        session = await db(
            lambda: GameSession.objects.filter(conversation_id=room["id"]).first()
        )
        check("but it does not start a game — they talk first", session is None)
        conversation = await db(lambda: Conversation.objects.get(pk=room["id"]))
        check("the room has an owner who can start one",
              conversation.owner_id in (a_id, b_id), str(conversation.owner_id))


async def main():
    wait_ready()
    await two_player_game()
    await group_game()
    await matched_rooms_do_not_autostart()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
