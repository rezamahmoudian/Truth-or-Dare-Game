"""WebSocket load test.

Two questions, because they fail for different reasons:

  1. **How many sockets can be open at once?** Every connection holds a
     channel-layer subscription and a Redis connection. Idle sockets are the
     cheap kind of load, but they are also the most numerous: most people have
     the app open and are not typing.

  2. **How long does a message take to reach the other people in the room,
     while all of that is going on?** Fan-out latency is what people actually
     feel; a chat that delivers in 40ms and one that delivers in 900ms are
     different products.

The second number is measured with several rooms talking at the same time,
because a single room tells you almost nothing. Every message in a busy room
is one database write plus one delivery per other player, and a busy evening
is many rooms doing that at once.

Run against the dev stack:

    docker compose exec -T backend python scripts/loadtest_ws.py
    docker compose exec -T backend python scripts/loadtest_ws.py --idle 500 --rooms 12
"""

import argparse
import asyncio
import contextlib
import json
import os
import pathlib
import secrets
import sys
import time

import django
import websockets

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rest_framework_simplejwt.tokens import RefreshToken  # noqa: E402

from apps.chat import services as chat_services  # noqa: E402
from apps.users.models import User  # noqa: E402

WS = "ws://localhost:8000/ws/"
ORIGIN = "http://localhost:8000"


def new_user(name: str) -> tuple[str, "User"]:
    """Create a player and mint their access token in-process.

    Not through `/api/auth/guest/`, on purpose: that endpoint is rate limited
    to 20/hour per address, which is the correct behaviour for a public signup
    and makes it useless for building a thousand players. The load test is
    about the socket layer, so it starts from users that already exist.
    """
    user = User.objects.create_user(
        username=f"load_{secrets.token_hex(6)}",
        display_name=name,
        gender="M",
        birth_date="1995-05-05",
    )
    return str(RefreshToken.for_user(user).access_token), user


async def connect(token: str):
    return await websockets.connect(
        WS, subprotocols=["ft.jwt", token], origin=ORIGIN, open_timeout=20
    )


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))
    return ordered[index]


async def open_idle_sockets(tokens: list[str]) -> tuple[list, float, int]:
    """Open a socket per token that just sits there, as most people's do."""
    count = len(tokens)
    started = time.perf_counter()
    results = await asyncio.gather(
        *(connect(token) for token in tokens), return_exceptions=True
    )
    elapsed = time.perf_counter() - started

    sockets = [r for r in results if not isinstance(r, Exception)]
    failures = count - len(sockets)

    # Drain each socket's `ready` frame so the buffers do not fill.
    async def drain(ws):
        with contextlib.suppress(Exception):
            while True:
                await asyncio.wait_for(ws.recv(), timeout=0.2)

    await asyncio.gather(*(drain(ws) for ws in sockets), return_exceptions=True)
    return sockets, elapsed, failures


def build_rooms(rooms: int, room_size: int) -> list[tuple[str, list[str]]]:
    """Create the rooms and their players before any measuring starts.

    Deliberately not done inside the async phase. Creating users and rooms
    blocks, so setting up room 5 while room 0 is already sending would stall
    the whole event loop, and the test would report the client's own stall as
    server latency. Ask me how I know.
    """
    built = []
    for index in range(rooms):
        players = [new_user(f"روم{index}-{i}") for i in range(room_size)]
        conversation = chat_services.create_room(players[0][1], max_players=room_size)
        for _, user in players[1:]:
            chat_services.join_by_code(user, conversation.code)
        built.append((str(conversation.id), [token for token, _ in players]))
    return built


async def measure_fanout(
    built: list[tuple[str, list[str]]], messages: int, room_size: int
) -> dict:
    """Latency from `chat.send` to the message arriving on the other sockets."""
    sent_at: dict[str, float] = {}
    latencies: list[float] = []

    # Connect everyone first, so the message phase contains nothing but
    # sending and receiving.
    connected: list[tuple[str, list]] = []
    for conversation_id, tokens in built:
        sockets = [await connect(token) for token in tokens]
        for ws in sockets:
            await ws.recv()  # ready
            await ws.send(
                json.dumps(
                    {
                        "type": "conv.subscribe",
                        "data": {"conversation_id": conversation_id},
                    }
                )
            )
        connected.append((conversation_id, sockets))
    await asyncio.sleep(1.0)

    delivered = 0

    async def listen(ws):
        nonlocal delivered
        with contextlib.suppress(Exception):
            while True:
                raw = await ws.recv()
                frame = json.loads(raw)
                if frame["type"] != "chat.message":
                    continue
                client_id = frame["data"].get("client_id")
                if client_id in sent_at:
                    latencies.append((time.perf_counter() - sent_at[client_id]) * 1000)
                    delivered += 1

    listeners = [
        asyncio.create_task(listen(ws))
        for _, sockets in connected
        for ws in sockets[1:]
    ]

    async def send_all(index: int, conversation_id: str, ws) -> None:
        for i in range(messages):
            client_id = f"load-{index}-{i}-{secrets.token_hex(3)}"
            sent_at[client_id] = time.perf_counter()
            await ws.send(
                json.dumps(
                    {
                        "type": "chat.send",
                        "data": {
                            "conversation_id": conversation_id,
                            "client_id": client_id,
                            "body": f"پیام تست شماره {i}",
                        },
                    }
                )
            )
            # Paced rather than blasted: this measures delivery, not how fast
            # the per-connection rate limiter refuses a flood.
            await asyncio.sleep(0.12)

    await asyncio.gather(
        *(
            send_all(index, conversation_id, sockets[0])
            for index, (conversation_id, sockets) in enumerate(connected)
        )
    )
    # Long enough that a slow tail counts as late rather than as lost.
    await asyncio.sleep(5.0)

    for task in listeners:
        task.cancel()
    for _, sockets in connected:
        for ws in sockets:
            with contextlib.suppress(Exception):
                await ws.close()

    return {
        "expected": len(connected) * messages * (room_size - 1),
        "delivered": delivered,
        "p50": percentile(latencies, 50),
        "p95": percentile(latencies, 95),
        "max": max(latencies) if latencies else 0.0,
    }


async def main(
    idle_tokens: list[str],
    built: list[tuple[str, list[str]]],
    room_size: int,
    messages: int,
) -> int:
    idle = len(idle_tokens)
    rooms = len(built)

    print(f"opening {idle} idle sockets…")
    sockets, elapsed, failures = await open_idle_sockets(idle_tokens)
    print(
        f"  connected {len(sockets)}/{idle} in {elapsed:.1f}s"
        f"  ({elapsed / max(1, idle) * 1000:.0f} ms each)"
    )
    if failures:
        print(f"  {failures} failed to connect")

    active = rooms * room_size
    print(
        f"\n{rooms} rooms talking at once ({active} active sockets),"
        f" {messages} messages each,"
        f"\nwhile {len(sockets)} idle sockets stay open"
        f" — {len(sockets) + active} connections in total…"
    )
    stats = await measure_fanout(built, messages, room_size)

    print(f"  delivered {stats['delivered']}/{stats['expected']} messages")
    print(f"  p50 {stats['p50']:6.0f} ms")
    print(f"  p95 {stats['p95']:6.0f} ms")
    print(f"  max {stats['max']:6.0f} ms")

    for ws in sockets:
        with contextlib.suppress(Exception):
            await ws.close()

    print()
    problems = []
    if failures:
        problems.append(f"{failures} sockets could not connect")
    if stats["delivered"] < stats["expected"]:
        problems.append(
            f"{stats['expected'] - stats['delivered']} messages were not delivered"
        )
    # A phone on mobile data adds its own latency; the server's share should be
    # small enough to disappear underneath it.
    if stats["p95"] > 1000:
        problems.append(f"p95 fan-out was {stats['p95']:.0f} ms")

    if problems:
        for problem in problems:
            print("PROBLEM:", problem)
        return 1
    print("no dropped messages, no failed connections, fan-out under a second.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--idle", type=int, default=200)
    parser.add_argument("--rooms", type=int, default=8)
    parser.add_argument("--room-size", type=int, default=8)
    parser.add_argument("--messages", type=int, default=25)
    args = parser.parse_args()

    # Everything that touches the database happens here, before the event loop
    # exists. Django refuses ORM calls from async context, and rightly so.
    print(f"creating {args.idle} idle players and {args.rooms} rooms…")
    idle_tokens = [new_user(f"بار {i}")[0] for i in range(args.idle)]
    prepared = build_rooms(args.rooms, args.room_size)

    raise SystemExit(
        asyncio.run(main(idle_tokens, prepared, args.room_size, args.messages))
    )
