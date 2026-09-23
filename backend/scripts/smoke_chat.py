"""End-to-end exercise of the phase 2 chat core: two users, two real sockets."""

import asyncio
import contextlib
import json
import secrets
import time
import urllib.error
import urllib.request

import websockets

BASE = "http://localhost:8000/api"
WS = "ws://localhost:8000/ws/"
# Browsers always send Origin; AllowedHostsOriginValidator rejects sockets
# without one, so this client has to imitate a browser to be a fair test.
ORIGIN = "http://localhost:8000"

results = []


def check(label, ok, detail=""):
    results.append((label, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def http(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        return err.code, json.loads(raw) if raw else None


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

def new_user(name, gender, birth):
    token = secrets.token_hex(24)
    _, data = http("POST", "/auth/guest/", body={"device_token": token})
    access = data["access"]
    http("PATCH", "/users/me/", access,
         {"display_name": name, "gender": gender, "birth_date": birth, "avatar": "a2"})
    return access, data["user"]["id"]


async def wait_http(fetch, check, timeout=8.0):
    """Poll an HTTP condition instead of sleeping a fixed amount.

    A fixed sleep makes a suite that passes alone and fails when the machine is
    busy — exactly when you are running everything at once.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        value = fetch()
        if check(value):
            return value
        await asyncio.sleep(0.15)
    return None


async def recv_until(ws, wanted, timeout=6.0, collect=False):
    """Read frames until one of `wanted` types arrives (or all, if collecting)."""
    seen = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return seen if collect else None
        try:
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
        except TimeoutError:
            return seen if collect else None
        seen.append(frame)
        if frame["type"] in wanted and not collect:
            return frame


async def main():
    wait_ready()
    a_token, a_id = new_user("آیدا", "F", "1996-04-12")
    b_token, b_id = new_user("بهرام", "M", "1994-08-02")
    check("two guest users created", a_id != b_id)

    status, room = http("POST", "/conversations/rooms/", a_token, {"max_players": 4})
    check("room created with join code", status == 201 and bool(room["code"]), room.get("code"))
    conv_id, code = room["id"], room["code"]

    status, joined = http("POST", "/conversations/join/", b_token, {"code": code})
    check("second user joined by code", status == 201 and joined["id"] == conv_id)

    status, _ = http("POST", "/conversations/join/", b_token, {"code": "ZZZZZZ"})
    check("bad code rejected", status == 404)

    async with websockets.connect(WS, subprotocols=["ft.jwt", a_token], origin=ORIGIN) as ws_a, \
               websockets.connect(WS, subprotocols=["ft.jwt", b_token], origin=ORIGIN) as ws_b:

        ready_a = json.loads(await ws_a.recv())
        ready_b = json.loads(await ws_b.recv())
        check("both sockets authenticated", ready_a["type"] == "ready" and ready_b["type"] == "ready")

        for ws in (ws_a, ws_b):
            await ws.send(json.dumps({"type": "conv.subscribe", "data": {"conversation_id": conv_id}}))

        presence = await recv_until(ws_a, {"presence"})
        online = set(presence["data"]["online_user_ids"]) if presence else set()
        check("presence lists both users", {a_id, b_id} <= online, str(sorted(online)))

        # --- send -------------------------------------------------------
        client_id = "c-" + secrets.token_hex(6)
        await ws_a.send(json.dumps({
            "type": "chat.send",
            "data": {"conversation_id": conv_id, "client_id": client_id, "body": "سلام!"},
        }))

        got_b = await recv_until(ws_b, {"chat.message"})
        check("message reached the other socket", got_b and got_b["data"]["body"] == "سلام!")
        message_id = got_b["data"]["id"]
        check("client_id echoed for reconciliation", got_b["data"]["client_id"] == client_id)

        frames_a = await recv_until(ws_a, set(), timeout=2.0, collect=True)
        types_a = [f["type"] for f in frames_a]
        check("sender also gets chat.message", "chat.message" in types_a)
        check("chat list update emitted", "conv.updated" in types_a, str(types_a))

        # --- idempotency -------------------------------------------------
        await ws_a.send(json.dumps({
            "type": "chat.send",
            "data": {"conversation_id": conv_id, "client_id": client_id, "body": "سلام!"},
        }))
        # Wait for the retry to have been processed, then assert it produced
        # no second row rather than assuming a fixed delay was enough.
        history = await wait_http(
            lambda: http("GET", f"/conversations/{conv_id}/messages/", a_token)[1],
            lambda h: any(m["client_id"] == client_id for m in h),
        ) or []
        await asyncio.sleep(0.5)
        _, history = http("GET", f"/conversations/{conv_id}/messages/", a_token)
        same = [m for m in history if m["client_id"] == client_id]
        check("retry with same client_id stored once", len(same) == 1, f"{len(same)} copies")

        # --- typing ------------------------------------------------------
        await ws_a.send(json.dumps({
            "type": "chat.typing", "data": {"conversation_id": conv_id, "is_typing": True},
        }))
        typing = await recv_until(ws_b, {"chat.typing"})
        check("typing reached the other socket", typing and typing["data"]["is_typing"] is True)

        # --- reactions ---------------------------------------------------
        await ws_b.send(json.dumps({
            "type": "chat.react", "data": {"message_id": message_id, "emoji": "😂", "op": "add"},
        }))
        reaction = await recv_until(ws_a, {"chat.reaction"})
        check("reaction broadcast", reaction and reaction["data"]["emoji"] == "😂")

        # --- read receipts -----------------------------------------------
        await ws_b.send(json.dumps({
            "type": "chat.read",
            "data": {"conversation_id": conv_id, "up_to_message_id": message_id},
        }))
        read = await recv_until(ws_a, {"chat.read"})
        check("read receipt broadcast", read and read["data"]["up_to_message_id"] == message_id)

        # --- unread counts -------------------------------------------------
        _, list_b = http("GET", "/conversations/", b_token)
        check("reader's unread is zero", list_b[0]["unread_count"] == 0, str(list_b[0]["unread_count"]))

        await ws_b.send(json.dumps({
            "type": "chat.send",
            "data": {"conversation_id": conv_id, "client_id": "c-" + secrets.token_hex(6),
                     "body": "سلام آیدا"},
        }))
        list_a = await wait_http(
            lambda: http("GET", "/conversations/", a_token)[1],
            lambda rows: rows and rows[0]["unread_count"] >= 1,
        )
        check("other side's unread incremented", bool(list_a),
              str(list_a[0]["unread_count"]) if list_a else "never incremented")

        # --- reconnect gap fill --------------------------------------------
        _, gap = http("GET", f"/conversations/{conv_id}/messages/?after={message_id}", a_token)
        check("gap fill returns only newer messages",
              all(m["id"] > message_id for m in gap) and len(gap) >= 1, f"{len(gap)} messages")

        # --- validation ------------------------------------------------------
        await ws_a.send(json.dumps({
            "type": "chat.send", "data": {"conversation_id": conv_id, "body": "   "},
        }))
        err = await recv_until(ws_a, {"error"})
        check("empty message rejected", err and err["data"]["code"] == "empty_message")

        await ws_a.send(json.dumps({"type": "nope", "data": {}}))
        err = await recv_until(ws_a, {"error"})
        check("unknown action rejected", err and err["data"]["code"] == "unknown_action")

    # --- room lifetime ------------------------------------------------------
    # A room outlives the people in it: it ends when its owner ends it, not
    # when everyone happens to close the tab.
    _, detail = http("GET", f"/conversations/{conv_id}/", a_token)
    check("the room has an owner", detail["owner_id"] == a_id, str(detail["owner_id"]))

    status, _ = http("POST", f"/conversations/{conv_id}/close/", b_token)
    check("a non-owner cannot close the room", status == 403, str(status))

    http("POST", f"/conversations/{conv_id}/leave/", b_token)
    _, detail = http("GET", f"/conversations/{conv_id}/", a_token)
    check("the room stays open after someone leaves",
          detail["status"] != "CLOSED", detail["status"])

    status, closed = http("POST", f"/conversations/{conv_id}/close/", a_token)
    check("the owner can close the room",
          status == 200 and closed["status"] == "CLOSED", str(status))

    status, _ = http("POST", f"/conversations/{conv_id}/messages/", a_token,
                     {"body": "هنوز اینجایی؟"})
    check("a closed room takes no new messages", status == 410, str(status))

    status, history = http("GET", f"/conversations/{conv_id}/messages/", a_token)
    check("a closed room keeps its history", status == 200 and len(history) > 0,
          f"{len(history)} messages")

    # --- deleting a conversation is per person --------------------------------
    d1_token, d1_id = new_user("پاک‌کن", "F", "1995-01-01")
    d2_token, d2_id = new_user("مخاطب", "M", "1995-01-01")
    _, delroom = http("POST", "/conversations/rooms/", d1_token, {"max_players": 4})
    http("POST", "/conversations/join/", d2_token, {"code": delroom["code"]})
    http("POST", f"/conversations/{delroom['id']}/messages/", d2_token,
         {"body": "سلام، این می‌ماند"})

    status, _ = http("DELETE", f"/conversations/{delroom['id']}/delete/", d1_token)
    check("a conversation can be deleted", status == 204, str(status))

    _, mine = http("GET", "/conversations/", d1_token)
    check("it leaves the deleter's chat list",
          not any(c["id"] == delroom["id"] for c in mine))

    _, theirs = http("GET", "/conversations/", d2_token)
    check("the other side still has it",
          any(c["id"] == delroom["id"] for c in theirs))

    _, kept = http("GET", f"/conversations/{delroom['id']}/messages/", d2_token)
    check("and every message in it", any(m["body"] == "سلام، این می‌ماند" for m in kept),
          f"{len(kept)} messages")

    # A private chat only hides — the other person can still reach you.
    f1_token, f1_id = new_user("دوست الف", "F", "1995-01-01")
    f2_token, f2_id = new_user("دوست ب", "M", "1995-01-01")
    http("POST", f"/friends/{f2_id}/", f1_token)
    _, accepted = http("POST", f"/friends/{f1_id}/accept/", f2_token)
    direct = accepted["conversation_id"]
    http("POST", f"/conversations/{direct}/messages/", f2_token, {"body": "پیام قدیمی"})

    http("DELETE", f"/conversations/{direct}/delete/", f1_token)
    _, mine = http("GET", "/conversations/", f1_token)
    check("a deleted private chat disappears too",
          not any(c["id"] == direct for c in mine))

    _, cleared = http("GET", f"/conversations/{direct}/messages/", f1_token)
    check("its old messages are hidden from the deleter", len(cleared) == 0,
          f"{len(cleared)} left")

    http("POST", f"/conversations/{direct}/messages/", f2_token, {"body": "هستی؟"})
    _, mine = http("GET", "/conversations/", f1_token)
    check("but a new message brings it back",
          any(c["id"] == direct for c in mine))
    _, after = http("GET", f"/conversations/{direct}/messages/", f1_token)
    check("showing only what arrived since",
          [m["body"] for m in after] == ["هستی؟"], str([m["body"] for m in after]))

    # --- ownership survives the owner leaving --------------------------------
    o_token, o_id = new_user("صاحب", "M", "1993-03-03")
    p_token, p_id = new_user("همراه", "F", "1994-04-04")
    _, room2 = http("POST", "/conversations/rooms/", o_token, {"max_players": 4})
    http("POST", "/conversations/join/", p_token, {"code": room2["code"]})

    http("POST", f"/conversations/{room2['id']}/leave/", o_token)
    _, detail2 = http("GET", f"/conversations/{room2['id']}/", p_token)
    check("ownership passes on when the owner leaves",
          detail2["owner_id"] == p_id, str(detail2["owner_id"]))
    check("the abandoned room is still open", detail2["status"] != "CLOSED",
          detail2["status"])

    status, _ = http("POST", f"/conversations/{room2['id']}/close/", p_token)
    check("the new owner can close it", status == 200, str(status))

    # --- authorisation ------------------------------------------------------
    c_token, _ = new_user("غریبه", "M", "1992-01-01")

    status, _ = http("POST", "/conversations/join/", c_token, {"code": code})
    check("nobody can join a closed room", status == 410, str(status))

    status, _ = http("GET", f"/conversations/{conv_id}/messages/", c_token)
    check("outsider cannot read the conversation", status == 403)

    ws = await websockets.connect(WS, subprotocols=["ft.jwt", "not-a-real-token"], origin=ORIGIN)
    frame = json.loads(await ws.recv())
    check("invalid token gets an error frame", frame["data"]["code"] == "unauthenticated", str(frame))
    with contextlib.suppress(Exception):
        await ws.recv()
    check("invalid token closed with 4401", ws.close_code == 4401, f"close_code={ws.close_code}")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
