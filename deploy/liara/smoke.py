"""Run only inside a disposable smoke container after startup.

Creates a test account and attachment; refuses non-test databases.
"""
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

database = urlsplit(os.environ.get("DATABASE_URL", ""))
if database.path != "/smoke" or not (database.hostname or "").startswith("ft-liara-smoke"):
    sys.exit("Refusing to modify a database outside the isolated Liara smoke environment.")
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.chat.attachments import private_storage
from apps.users.models import User
from rest_framework_simplejwt.tokens import AccessToken
from apps.matchmaking.tasks import run_matcher
from websockets.asyncio.client import connect

base = "http://127.0.0.1:3000"


def request(path, data=None, headers=None):
    req = Request(base + path, data=data, headers={"Host": "localhost", **(headers or {})})
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, response.headers, response.read()


status, _, body = request("/api/health/")
assert status == 200 and json.loads(body)["status"] == "ok"
for path in ("/", "/chat", "/friends"):
    status, _, body = request(path)
    assert status == 200 and b'<div id="root">' in body, path
status, headers, body = request("/admin/login/", headers={"X-Forwarded-Proto": "https"})
assert status == 200 and b"csrfmiddlewaretoken" in body
assert "Secure" in headers.get("Set-Cookie", "")
csrf = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', body)[1].decode()
cookie = headers.get("Set-Cookie").split(";")[0]
status, _, body = request("/admin/login/", data=urlencode({
    "username": "nonexistent-smoke-user", "password": "invalid", "csrfmiddlewaretoken": csrf,
}).encode(), headers={"Cookie": cookie, "Origin": "https://localhost", "X-Forwarded-Proto": "https",
                     "Content-Type": "application/x-www-form-urlencoded"})
assert status == 200, "HTTPS proxy/CSRF handling failed"
status, headers, body = request("/static/admin/css/base.css")
assert status == 200 and "text/css" in headers.get("Content-Type", "") and len(body) > 100
for path in ("/.env", "/private_media/test.txt", "/media/test.txt"):
    assert request(path)[0] == 404, path
assert request("/sw.js")[1].get("Cache-Control") == "no-cache"
assert not Path("/app/.env").exists() and not Path("/.env").exists()
subprocess.run(["python", "/app/deploy/liara/healthcheck.py"], check=True)
print("PASS: frontend routes, API, admin/CSS/CSRF, private paths and process health", flush=True)

user = User.objects.create_user(username="liara-smoke-" + uuid.uuid4().hex[:12], password=None)
token = str(AccessToken.for_user(user))


async def check_socket():
    async with connect("ws://127.0.0.1:3000/ws/", origin="https://localhost",
                       subprotocols=["ft.jwt", token], open_timeout=10) as socket:
        ready = json.loads(await asyncio.wait_for(socket.recv(), 10))
        assert ready["type"] == "ready" and ready["data"]["user_id"] == user.pk
        await socket.send(json.dumps({"type": "ping"}))
        reply = json.loads(await asyncio.wait_for(socket.recv(), 10))
        assert reply["type"] == "pong", reply["type"]


asyncio.run(check_socket())
print("PASS: authenticated WebSocket through nginx and Redis presence", flush=True)
result = run_matcher.apply_async(ignore_result=False)
result.get(timeout=25)
result.forget()
print("PASS: real matchmaking task executed by Celery worker", flush=True)
subprocess.run(["gosu", "app", "python", "-c",
                "from pathlib import Path; p=Path('/app/private_media/smoke'); "
                "p.mkdir(exist_ok=True); (p/'persistence.txt').write_bytes(b'persistent-test-file')"], check=True)
assert private_storage().open("smoke/persistence.txt").read() == b"persistent-test-file"
print("PASS: private upload volume is writable", flush=True)
