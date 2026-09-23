"""End-to-end exercise of the phase 6 safety layer.

Two halves. The first is the word filter, where the interesting cases are the
ones that must *not* fire: Persian obscenities are spelled inside ordinary
words, and a filter that masks "عکس" gets switched off by whoever runs the
product. The second is reporting, blocking and message removal, including what
blocking has to undo.
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.chat.models import Message  # noqa: E402
from apps.moderation.filters import screen  # noqa: E402
from apps.users.models import Friendship, Report, User  # noqa: E402

BASE = "http://localhost:8000/api"

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
         {"display_name": name, "gender": gender, "birth_date": "1995-05-05", "avatar": "a2"})
    return token, data["user"]["id"]


async def db(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


async def main():
    wait_ready()
    # ---------------------------------------------------------------- filter
    # These are the ones that matter. Every phrase here is innocent and
    # contains the letters of an obscenity; a false positive on any of them is
    # worse than a miss, because it makes the app look broken to everyone.
    innocent = [
        "این عکس خیلی قشنگه",
        "هرکسی بیاد خوش اومده",
        "عشق یعنی همین",
        "اکنون وقتشه",
        "دختر خاله‌م اومده",
        "مشقامو ننوشتم",
        "کسی اینجا نیست؟",
        "آخرین باری که خریدم",
    ]
    clean = await db(lambda: [screen(text).clean for text in innocent])
    failures = [text for text, ok in zip(innocent, clean, strict=True) if not ok]
    check("ordinary Persian is left alone", not failures, "; ".join(failures))

    # Evasion: variant spellings, padding and separators all reach the same word.
    evasions = ["کثافت", "كثافت", "کثاااافت", "ک ث ا ف ت", "ک.ث.ا.ف.ت", "کثا‌فت"]
    caught = await db(lambda: [not screen(text).clean for text in evasions])
    missed = [text for text, ok in zip(evasions, caught, strict=True) if not ok]
    check("spelling tricks do not get past the filter", not missed, "; ".join(missed))

    masked = await db(lambda: screen("تو خیلی احمقی نه، احمق"))
    check("masking keeps the rest of the sentence",
          masked.masked and "***" in masked.text and "نه" in masked.text, masked.text)
    check("Persian suffixes are covered too",
          "احمقی" not in masked.text, masked.text)

    # The suffix rule must not reach the short words it was kept away from.
    short = await db(lambda: [screen(t).clean for t in ["کسی اینجاست", "گهگاه میاد", "کسانی که"]])
    check("suffix tolerance stops short of the ambiguous stems", all(short), str(short))

    blocked = await db(lambda: screen("کیر"))
    check("the worst terms are refused, not masked",
          blocked.blocked and not blocked.masked)

    # ------------------------------------------------------------ in a room
    a_token, a_id = new_user("آیدا", "F")
    b_token, b_id = new_user("بهرام", "M")
    _, room = http("POST", "/conversations/rooms/", a_token, {"max_players": 4})
    http("POST", "/conversations/join/", b_token, {"code": room["code"]})
    conv = room["id"]

    status, message = http("POST", f"/conversations/{conv}/messages/", a_token,
                           {"body": "احمق نباش، این عکس قشنگه"})
    check("a masked message is still delivered", status == 201, str(status))
    check("but the word is gone from what was stored",
          "***" in message["body"] and "عکس" in message["body"], message["body"])

    status, _ = http("POST", f"/conversations/{conv}/messages/", a_token, {"body": "کیر"})
    check("a refused message never reaches the room", status == 422, str(status))

    # ----------------------------------------------------------- reporting
    status, _ = http("POST", "/reports/", a_token,
                     {"target_user_id": b_id, "reason": "NOT_A_REASON"})
    check("an invalid reason is rejected", status == 400, str(status))

    status, _ = http("POST", "/reports/", a_token,
                     {"target_user_id": a_id, "reason": "SPAM"})
    check("you cannot report yourself", status == 400, str(status))

    _, sent = http("POST", f"/conversations/{conv}/messages/", b_token,
                   {"body": "یه پیام معمولی"})
    status, _ = http("POST", "/reports/", a_token,
                     {"target_user_id": b_id, "reason": "HARASSMENT",
                      "message_id": sent["id"], "note": "بی‌احترامی کرد"})
    check("a report about a message is filed", status == 201, str(status))

    row = await db(lambda: Report.objects.filter(target_user_id=b_id).last())
    check("the report keeps the message it is about",
          row is not None and row.target_message_id == sent["id"])
    check("reports start unreviewed — nothing is automatic",
          row is not None and row.status == "OPEN", row.status if row else "")

    # An outsider must not be able to report a message they never saw.
    c_token, _ = new_user("غریبه", "M")
    status, _ = http("POST", "/reports/", c_token,
                     {"target_user_id": b_id, "reason": "SPAM",
                      "message_id": sent["id"]})
    check("you cannot report a message from a room you were not in",
          status == 403, str(status))

    # ------------------------------------------------------ message removal
    status, deleted = http("DELETE", f"/messages/{sent['id']}/", a_token)
    check("you cannot delete someone else's message", status == 403, str(status))

    status, deleted = http("DELETE", f"/messages/{sent['id']}/", b_token)
    check("you can delete your own", status == 200 and deleted["is_deleted"], str(status))
    check("the body is withheld once deleted", deleted["body"] == "", deleted["body"])

    stored = await db(lambda: Message.objects.get(pk=sent["id"]))
    check("but the text is kept for the moderator who reads the report",
          stored.body != "", stored.body)

    # ------------------------------------------------------------- blocking
    d_token, d_id = new_user("دوست", "F")
    http("POST", f"/friends/{d_id}/", a_token)
    _, accepted = http("POST", f"/friends/{a_id}/accept/", d_token)
    direct = accepted["conversation_id"]

    status, _ = http("POST", f"/conversations/{direct}/messages/", a_token,
                     {"body": "سلام"})
    check("friends can message privately", status == 201, str(status))

    status, _ = http("POST", f"/blocks/{d_id}/", a_token)
    check("blocking works", status == 204, str(status))

    remaining = await db(
        lambda: Friendship.objects.filter(
            from_user_id__in=[a_id, d_id], to_user_id__in=[a_id, d_id]
        ).count()
    )
    check("blocking removes the friendship", remaining == 0, str(remaining))

    status, _ = http("POST", f"/conversations/{direct}/messages/", a_token,
                     {"body": "بازم سلام"})
    check("the blocker cannot message them", status == 403, str(status))

    status, _ = http("POST", f"/conversations/{direct}/messages/", d_token,
                     {"body": "چی شد؟"})
    check("and neither can the blocked person", status == 403, str(status))

    status, _ = http("POST", f"/friends/{d_id}/", a_token)
    check("a blocked pair cannot become friends", status == 403, str(status))

    _, blocked_list = http("GET", "/blocks/", a_token)
    check("the blocked list is visible", any(p["id"] == d_id for p in blocked_list))

    status, _ = http("DELETE", f"/blocks/{d_id}/", a_token)
    check("unblocking works", status == 204, str(status))
    status, _ = http("POST", f"/conversations/{direct}/messages/", a_token,
                     {"body": "برگشتم"})
    check("messaging works again afterwards", status == 201, str(status))

    # ---------------------------------------------------------------- bans
    banned_token, banned_id = new_user("مسدود", "M")
    await db(lambda: User.objects.filter(pk=banned_id).update(is_active=False))
    status, _ = http("GET", "/users/me/", banned_token)
    check("a deactivated account cannot use its existing token",
          status in (401, 403), str(status))

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


with contextlib.suppress(KeyboardInterrupt):
    raise SystemExit(asyncio.run(main()))
