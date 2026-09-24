"""Count the database queries behind each screen.

Written because the alternative is guessing. An N+1 does not show up on a
developer's laptop with four rows in the table; it shows up as a slow app three
months after launch, on the screen people open most.

Each case builds a realistic amount of data first, then reports how many
queries the endpoint actually runs. The number to watch is not the absolute
count but whether it grows with the data.
"""

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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, reset_queries  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from apps.chat import services as chat_services  # noqa: E402
from apps.game import services as game_services  # noqa: E402
from apps.matchmaking import services as mm_services  # noqa: E402
from apps.users import social  # noqa: E402
from apps.users.models import User  # noqa: E402

BASE = "http://localhost:8000/api"

results: list[tuple[str, int, int, str]] = []


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
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.suppress(Exception):
            if http("GET", "/health/")[0] == 200:
                return
        time.sleep(0.5)
    raise SystemExit("API did not become ready")


def new_user(name, gender="M"):
    _, data = http("POST", "/auth/guest/", body={"device_token": secrets.token_hex(24)})
    token = data["access"]
    http(
        "PATCH",
        "/users/me/",
        token,
        {"display_name": name, "gender": gender, "birth_date": "1995-05-05", "avatar": "a3"},
    )
    return token, data["user"]["id"]


def measure(label, fn, *, scale: str) -> int:
    """Run `fn` once (warm) then count the queries of a second run."""
    fn()
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        fn()
    count = len(ctx.captured_queries)
    results.append((label, count, 0, scale))
    return count


def build_world(rooms: int, friends: int, messages: int):
    """A user with a realistic amount of history behind them."""
    owner = User.objects.create_user(
        username=f"perf_{secrets.token_hex(4)}",
        display_name="کاربر سنگین",
        gender="M",
        birth_date="1995-05-05",
    )

    for i in range(rooms):
        other = User.objects.create_user(
            username=f"perf_o_{secrets.token_hex(4)}",
            display_name=f"همبازی {i}",
            gender="F",
            birth_date="1996-06-06",
        )
        conversation = chat_services.create_room(owner, max_players=4)
        chat_services.join_by_code(other, conversation.code)
        for m in range(messages):
            chat_services.post_message(
                conversation=conversation,
                sender=other if m % 2 else owner,
                body=f"پیام شماره {m}",
            )

    for i in range(friends):
        friend = User.objects.create_user(
            username=f"perf_f_{secrets.token_hex(4)}",
            display_name=f"دوست {i}",
            gender="F",
            birth_date="1996-06-06",
        )
        social.send_request(owner, friend.pk)
        social.accept_request(friend, owner.pk)

    return owner


def main():
    wait_ready()
    print("building a small world (5 rooms, 5 friends)…")
    small = build_world(rooms=5, friends=5, messages=6)
    print("building a larger one (20 rooms, 20 friends)…")
    large = build_world(rooms=20, friends=20, messages=6)

    print()
    print(f"{'endpoint':42} {'5 rooms':>9} {'20 rooms':>9}   verdict")
    print("-" * 78)

    checks = [
        (
            "chat list  (conversations_for)",
            lambda u: lambda: [
                [m.user for m in c.active_members]
                for c in chat_services.conversations_for(u, with_participants=True)
            ],
        ),
        (
            "friends    (friends_of + requests)",
            lambda u: lambda: (
                social.friends_of(u),
                social.incoming_requests(u),
                social.outgoing_requests(u),
            ),
        ),
        (
            "lobby      (modes + presence)",
            lambda u: lambda: (
                mm_services.queue_sizes(),
                mm_services.online_count(),
                mm_services.recently_active(),
            ),
        ),
        (
            "history    (50 messages)",
            lambda u: lambda: [
                chat_services.history(c, limit=50)
                for c in list(chat_services.conversations_for(u))[:1]
            ],
        ),
        (
            "game state (state_of)",
            lambda u: lambda: [
                game_services.state_of(c.id)
                for c in list(chat_services.conversations_for(u))[:1]
            ],
        ),
    ]

    problems = []
    for label, make in checks:
        reset_queries()
        with CaptureQueriesContext(connection) as ctx:
            make(small)()
        few = len(ctx.captured_queries)

        reset_queries()
        with CaptureQueriesContext(connection) as ctx:
            make(large)()
        many = len(ctx.captured_queries)

        # Four times the data must not mean four times the queries.
        grew = many > few * 2
        verdict = "N+1 — grows with data" if grew else "flat"
        if grew:
            problems.append(label)
        print(f"{label:42} {few:>9} {many:>9}   {verdict}")

    print()
    if problems:
        print("queries that scale with the data:")
        for p in problems:
            print("  -", p)
    else:
        print("no query count grew with the data.")
    return 1 if problems else 0


raise SystemExit(main())
