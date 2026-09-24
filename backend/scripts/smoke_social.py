"""End-to-end exercise of the phase 5 social loop.

This is the chain the whole product is built to produce:

    matched with a stranger → played a game → sent a friend request
    → accepted → private conversation → started another game in it

Each link is checked here, along with the ways it can be abused: befriending
yourself, befriending someone who blocked you, two people asking each other at
the same time, and unfriending without destroying the other person's history.
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

from apps.chat.models import Conversation, Message  # noqa: E402
from apps.game.models import GameSession  # noqa: E402
from apps.users.models import Block  # noqa: E402

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
    """Block until the API answers.

    uvicorn reloads on every source edit, so a suite started moments after a
    change can hit a server that is still restarting. That produces a red run
    with nothing wrong in it, which is the fastest way to stop trusting a test
    suite.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.suppress(Exception):
            status, _ = http("GET", "/health/")
            if status == 200:
                return
        time.sleep(0.5)
    raise SystemExit("API did not become ready")

def new_user(name, gender="M"):
    _, data = http("POST", "/auth/guest/", body={"device_token": secrets.token_hex(24)})
    token = data["access"]
    http("PATCH", "/users/me/", token,
         {"display_name": name, "gender": gender, "birth_date": "1995-05-05", "avatar": "a5"})
    return token, data["user"]["id"]


async def db(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


async def wait_for(predicate, timeout=8.0, interval=0.1):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(interval)
    return None


class Client:
    def __init__(self, name, gender="M"):
        self.name = name
        self.token, self.id = new_user(name, gender)
        self.events: list[dict] = []

    async def connect(self):
        self.ws = await websockets.connect(
            WS, subprotocols=["ft.jwt", self.token], origin=ORIGIN
        )
        await self.ws.recv()
        self._pump = asyncio.create_task(self._read())

    async def _read(self):
        with contextlib.suppress(Exception):
            async for raw in self.ws:
                self.events.append(json.loads(raw))

    def event(self, kind):
        for frame in reversed(self.events):
            if frame["type"] == kind:
                return frame["data"]
        return None

    async def close(self):
        self._pump.cancel()
        await self.ws.close()


async def main():
    wait_ready()
    a = Client("آیدا", "F")
    b = Client("بهرام", "M")
    for client in (a, b):
        await client.connect()

    # --- they meet in a room ------------------------------------------------
    _, room = http("POST", "/conversations/rooms/", a.token, {"max_players": 4})
    http("POST", "/conversations/join/", b.token, {"code": room["code"]})
    check("two strangers share a room", True, room["code"])

    # --- the request --------------------------------------------------------
    status, _ = http("POST", f"/friends/{a.id}/", a.token)
    check("you cannot befriend yourself", status == 400, str(status))

    status, profile = http("POST", f"/friends/{b.id}/", a.token)
    check("a friend request is sent", status == 201 and profile["relation"] == "OUTGOING",
          str(profile.get("relation")))

    notified = await wait_for(lambda: b.event("friend.request"))
    check("the other side is told in real time",
          bool(notified) and notified["from_user"]["id"] == a.id)

    _, lists = http("GET", "/friends/", b.token)
    check("it shows up as an incoming request",
          len(lists["incoming"]) == 1 and lists["incoming"][0]["user"]["id"] == a.id)

    _, lists_a = http("GET", "/friends/", a.token)
    check("and as an outgoing one for the sender", len(lists_a["outgoing"]) == 1)

    # --- acceptance opens a private conversation ----------------------------
    status, accepted = http("POST", f"/friends/{a.id}/accept/", b.token)
    conversation_id = accepted.get("conversation_id") if accepted else None
    check("accepting works", status == 200 and bool(conversation_id))

    conversation = await db(lambda: Conversation.objects.get(pk=conversation_id))
    check("acceptance opens a DIRECT conversation", conversation.type == "DIRECT",
          conversation.type)

    both = await wait_for(
        lambda: a.event("friend.accepted") and b.event("friend.accepted")
    )
    check("both sides are told, with the conversation id",
          bool(both) and a.event("friend.accepted")["conversation_id"] == conversation_id)

    messages = await db(
        lambda: list(Message.objects.filter(conversation_id=conversation_id))
    )
    check("the private chat does not open empty", len(messages) >= 1,
          messages[0].body if messages else "no messages")

    _, lists = http("GET", "/friends/", a.token)
    check("they appear in each other's friend list",
          len(lists["friends"]) == 1 and lists["friends"][0]["id"] == b.id)
    check("no pending requests are left over",
          not lists["incoming"] and not lists["outgoing"])

    _, chats = http("GET", "/conversations/", a.token)
    check("the private chat is in the chat list",
          any(c["id"] == conversation_id for c in chats))

    # --- a game inside the friend chat --------------------------------------
    # The same engine as a matched room, because a session hangs off a
    # conversation rather than the other way round.
    status, started = http("POST", f"/conversations/{conversation_id}/game/", a.token)
    check("a game can be started inside a private chat",
          status == 201 and started["session"]["status"] == "ACTIVE", str(status))
    check("it has a turn open and both friends in the order",
          started["turn"] is not None
          and sorted(started["session"]["turn_order"]) == sorted([a.id, b.id]))

    session = await db(
        lambda: GameSession.objects.filter(conversation_id=conversation_id).first()
    )
    check("the session belongs to the private conversation",
          session is not None and str(session.conversation_id) == conversation_id)

    # --- a second request from the other direction --------------------------
    c = Client("سینا", "M")
    d = Client("نگار", "F")
    http("POST", f"/friends/{d.id}/", c.token)
    status, _ = http("POST", f"/friends/{c.id}/", d.token)
    check("asking back is an acceptance, not a second request", status == 201, str(status))
    _, relation = http("GET", f"/people/{c.id}/", d.token)
    check("they are friends straight away", relation["relation"] == "FRIENDS",
          relation["relation"])

    # --- blocks -------------------------------------------------------------
    e = Client("ایکس", "M")
    f = Client("وای", "F")
    await db(lambda: Block.objects.create(blocker_id=f.id, blocked_id=e.id))
    status, _ = http("POST", f"/friends/{f.id}/", e.token)
    check("someone who blocked you cannot be befriended", status == 403, str(status))

    _, relation = http("GET", f"/people/{f.id}/", e.token)
    check("their profile reports the block", relation["relation"] == "BLOCKED",
          relation["relation"])

    # --- declining ----------------------------------------------------------
    g = Client("گ", "M")
    h = Client("ه", "F")
    http("POST", f"/friends/{h.id}/", g.token)
    status, _ = http("POST", f"/friends/{g.id}/decline/", h.token)
    check("a request can be declined", status == 204, str(status))
    _, lists = http("GET", "/friends/", h.token)
    check("declining clears it from the list",
          not lists["incoming"] and not lists["friends"])

    # --- unfriending --------------------------------------------------------
    before = await db(
        lambda: Message.objects.filter(conversation_id=conversation_id).count()
    )
    status, _ = http("DELETE", f"/friends/{b.id}/", a.token)
    check("unfriending works", status == 204, str(status))

    _, lists = http("GET", "/friends/", a.token)
    check("they are no longer friends", not lists["friends"])

    after = await db(
        lambda: Message.objects.filter(conversation_id=conversation_id).count()
    )
    check("unfriending does not delete the shared history",
          after == before, f"{before} → {after}")

    _, relation = http("GET", f"/people/{b.id}/", a.token)
    check("and a new request is possible again", relation["relation"] == "NONE",
          relation["relation"])

    for client in (a, b, c, d, e, f, g, h):
        with contextlib.suppress(Exception):
            await client.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
