"""End-to-end exercise of the phase 4 matchmaker.

Covers the parts that decide whether this product feels alive: a pair matching
at all, the two gender-filtered queues being two views of one match, constraint
widening rescuing a starved queue, group rooms filling, blocked and
recently-played pairs being skipped, the daily cap, and tickets expiring with a
suggestion instead of spinning forever.

The first case waits on the real Celery beat tick so the scheduled path is
actually proven. The rest call the matcher directly, because asserting "these
two must NOT match" against a background scheduler is a race, not a test.
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

from django.conf import settings  # noqa: E402

from apps.chat.models import Conversation, Participant  # noqa: E402
from apps.game.models import GameSession  # noqa: E402
from apps.matchmaking import services as mm  # noqa: E402
from apps.matchmaking.models import MatchMode, MatchTicket, TicketState  # noqa: E402
from apps.users.models import Block, User  # noqa: E402

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

def new_user(name, gender):
    _, data = http("POST", "/auth/guest/", body={"device_token": secrets.token_hex(24)})
    token = data["access"]
    http("PATCH", "/users/me/", token,
         {"display_name": name, "gender": gender, "birth_date": "1995-05-05", "avatar": "a3"})
    return token, data["user"]["id"]


async def db(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


async def wait_for(predicate, timeout=12.0, interval=0.2):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        value = await db(predicate)
        if value:
            return value
        await asyncio.sleep(interval)
    return None


class Client:
    """A queued user holding a socket, collecting mm.* events."""

    def __init__(self, name, gender):
        self.name, self.gender = name, gender
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
                frame = json.loads(raw)
                if frame["type"].startswith("mm."):
                    self.events.append(frame)

    async def enqueue(self, mode):
        await self.ws.send(json.dumps({"type": "mm.enqueue", "data": {"mode": mode}}))

    def event(self, kind):
        for frame in reversed(self.events):
            if frame["type"] == kind:
                return frame["data"]
        return None

    async def close(self):
        self._pump.cancel()
        await self.ws.close()


def ticket_of(user_id):
    return MatchTicket.objects.filter(user_id=user_id).order_by("-id").first()


def conversation_count(user_id):
    return Participant.objects.filter(user_id=user_id).count()


def set_widen(mode_key, seconds):
    """Modes are data — the test tunes one the same way an operator would."""
    MatchMode.objects.filter(key=mode_key).update(widen_after_seconds=seconds)


def drain_queue():
    """Start from an empty queue.

    Tickets left over from an interrupted run would be matched with this run's
    users by the background matcher, and the failure looks like a bug in the
    matcher rather than in the fixture.
    """
    return MatchTicket.objects.filter(state=TicketState.QUEUED).update(
        state=TicketState.CANCELLED
    )


async def main():
    wait_ready()
    await db(drain_queue)

    # Beat keeps matching in the background throughout this run. Anything the
    # test needs to observe as *not* matched therefore has to be genuinely
    # unmatchable, not merely young — so widening is pushed out of reach and
    # lowered only for the cases that are about widening.
    for key in ("quick", "girls", "boys", "group", "deep"):
        await db(set_widen, key, 3600)

    # ---------------------------------------------------------------- pair
    await db(set_widen, "quick", 20)
    a, b = Client("آیدا", "F"), Client("بهرام", "M")
    for client in (a, b):
        await client.connect()
    await a.enqueue("quick")
    await b.enqueue("quick")

    matched = await wait_for(
        lambda: a.event("mm.matched") and b.event("mm.matched"), timeout=15
    )
    check("two people in the quick queue are matched by the scheduled matcher",
          bool(matched))

    if matched:
        room_a = a.event("mm.matched")["conversation_id"]
        room_b = b.event("mm.matched")["conversation_id"]
        check("both land in the same room", room_a == room_b, room_a)
        check("each is in exactly one room",
              await db(conversation_count, a.id) == 1
              and await db(conversation_count, b.id) == 1)

        # No game starts here any more. Two strangers dropped straight into a
        # turn have to perform before they have said hello; the room owner
        # starts one when they are ready.
        session = await db(
            lambda: GameSession.objects.filter(conversation_id=room_a).first()
        )
        check("the room opens without a game running", session is None)

        conversation = await db(lambda: Conversation.objects.get(pk=room_a))
        check("and it has an owner who can start one",
              conversation.owner_id in (a.id, b.id), str(conversation.owner_id))

    # ------------------------------------------------- gender, two directions
    # These two satisfy each other's filter outright, so no widening is needed.
    f, m = Client("نگار", "F"), Client("سینا", "M")
    for client in (f, m):
        await client.connect()
    await f.enqueue("boys")   # a woman looking for a man
    await m.enqueue("girls")  # a man looking for a woman

    matched = await wait_for(
        lambda: f.event("mm.matched") and m.event("mm.matched"), timeout=15
    )
    check("the two gender queues are one match seen from both sides", bool(matched))

    # ------------------------------------------- a starved queue, then widening
    m1, m2 = Client("مرد ۱", "M"), Client("مرد ۲", "M")
    for client in (m1, m2):
        await client.connect()
    await m1.enqueue("girls")
    await m2.enqueue("girls")
    await asyncio.sleep(0.5)

    await db(mm.run_matcher)
    still_waiting = await db(
        lambda: MatchTicket.objects.filter(
            user_id__in=[m1.id, m2.id], state=TicketState.QUEUED
        ).count()
    )
    check("two men both asking for a woman are not matched with each other",
          still_waiting == 2, f"{still_waiting} still queued")

    # Now let widening happen: the same two tickets become matchable.
    await db(set_widen, "girls", 0)
    await db(mm.run_matcher)
    await db(mm.run_matcher)
    matched = await wait_for(
        lambda: m1.event("mm.matched") and m2.event("mm.matched"), timeout=8
    )
    check("widening rescues a queue that cannot be satisfied as asked",
          bool(matched))
    if matched:
        ticket = await db(ticket_of, m1.id)
        check("the user was told the search had widened", ticket.widened)

    # ------------------------------------------------------------- group room
    group = [Client(f"گروه {i}", "M" if i % 2 else "F") for i in range(3)]
    for client in group:
        await client.connect()
        await client.enqueue("group")
    await db(set_widen, "group", 0)
    await db(mm.run_matcher)
    await db(mm.run_matcher)

    matched = await wait_for(
        lambda: all(c.event("mm.matched") for c in group), timeout=10
    )
    check("a group room forms at its minimum size once widened", bool(matched))
    if matched:
        rooms = {c.event("mm.matched")["conversation_id"] for c in group}
        check("the whole group lands in one room", len(rooms) == 1, str(len(rooms)))

    # ------------------------------------------------------------------ blocks
    # Unwidenable for the duration, so "not matched" means the block did it.
    await db(set_widen, "quick", 3600)
    x, y = Client("ایکس", "M"), Client("وای", "F")
    for client in (x, y):
        await client.connect()
    await db(lambda: Block.objects.create(blocker_id=x.id, blocked_id=y.id))
    await x.enqueue("quick")
    await y.enqueue("quick")
    await asyncio.sleep(0.5)
    await db(mm.run_matcher)
    await db(mm.run_matcher)

    queued = await db(
        lambda: MatchTicket.objects.filter(
            user_id__in=[x.id, y.id], state=TicketState.QUEUED
        ).count()
    )
    check("a blocked pair is never matched", queued == 2, f"{queued} still queued")
    await db(lambda: mm.cancel(User.objects.get(pk=x.id)))
    await db(lambda: mm.cancel(User.objects.get(pk=y.id)))

    # --------------------------------------------------------- recent partners
    if matched:
        pair = group[:2]
        for client in pair:
            await client.enqueue("quick")
        await asyncio.sleep(0.5)
        await db(mm.run_matcher)
        queued = await db(
            lambda: MatchTicket.objects.filter(
                user_id__in=[c.id for c in pair], state=TicketState.QUEUED
            ).count()
        )
        check("two people who just played are not handed each other again",
              queued == 2, f"{queued} still queued")
        for client in pair:
            await db(lambda cid=client.id: mm.cancel(User.objects.get(pk=cid)))

    # -------------------------------------------------------------- duplicates
    d = Client("تکراری", "F")
    await d.connect()
    status, first = http("POST", "/match/", d.token, {"mode": "quick"})
    _, second = http("POST", "/match/", d.token, {"mode": "quick"})
    check("enqueueing twice returns the same ticket",
          status == 201 and first["id"] == second["id"], str(first["id"]))
    tickets = await db(
        lambda: MatchTicket.objects.filter(
            user_id=d.id, state=TicketState.QUEUED
        ).count()
    )
    check("nobody sits in the queue twice", tickets == 1, str(tickets))

    status, _ = http("DELETE", "/match/", d.token)
    left = await db(
        lambda: MatchTicket.objects.filter(
            user_id=d.id, state=TicketState.QUEUED
        ).count()
    )
    check("cancelling leaves the queue", status == 204 and left == 0)

    # ------------------------------------------------------------ daily limit
    limited = Client("محدود", "M")
    await limited.connect()
    codes = []
    for _ in range(4):
        code, _body = http("POST", "/match/", limited.token, {"mode": "girls"})
        codes.append(code)
        http("DELETE", "/match/", limited.token)
    check("the daily cap on the scarce queue is enforced",
          codes[:3] == [201, 201, 201] and codes[3] == 429, str(codes))

    _, modes = http("GET", "/match-modes/", limited.token)
    girls = next(m for m in modes if m["key"] == "girls")
    check("the mode list reports what is left of the cap",
          girls["remaining_today"] == 0, str(girls["remaining_today"]))

    # ----------------------------------------------------------------- expiry
    lonely = Client("تنها", "F")
    await lonely.connect()
    await lonely.enqueue("deep")
    await asyncio.sleep(0.6)

    original_ttl = settings.MATCH_TICKET_TTL_SECONDS
    settings.MATCH_TICKET_TTL_SECONDS = 1
    try:
        await asyncio.sleep(1.2)
        await db(mm.run_matcher)
        expired = await wait_for(lambda: lonely.event("mm.expired"), timeout=6)
    finally:
        settings.MATCH_TICKET_TTL_SECONDS = original_ttl

    check("a ticket that waits too long expires", bool(expired))
    check("expiry names a queue that actually fills",
          bool(expired) and expired.get("suggested_mode") == "group",
          str(expired))

    # ------------------------------------------------------------- data-driven
    _, modes = http("GET", "/match-modes/", a.token)
    featured = [m["key"] for m in modes if m["is_featured"]]
    check("modes come from the database, not the client", len(modes) >= 5, str(len(modes)))
    check("the queues that fill are the ones featured",
          set(featured) == {"quick", "group"}, str(featured))

    for client in [a, b, f, m, m1, m2, x, y, d, limited, lonely, *group]:
        with contextlib.suppress(Exception):
            await client.close()

    for key in ("quick", "girls", "boys", "group", "deep"):
        await db(set_widen, key, 20)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
