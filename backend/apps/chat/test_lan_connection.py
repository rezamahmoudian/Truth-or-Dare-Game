import json
from datetime import date
from unittest.mock import patch

from asgiref.testing import ApplicationCommunicator
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.conf import settings
from django.test import TransactionTestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from apps.chat.ws_auth import JWTAuthMiddleware
from apps.matchmaking import services
from apps.matchmaking.models import MatchMode
from apps.users.models import User
from config.routing import websocket_urlpatterns


@override_settings(AI_PLAYERS_ENABLED=False, CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class LanConnectionTests(TransactionTestCase):
    def setUp(self):
        self.users = [User.objects.create_user(username=f"lan-{i}", display_name=f"بازیکن {i}", gender=gender, birth_date=date(1995, 1, 1)) for i, gender in enumerate(("M", "F"))]
        self.tokens = [str(AccessToken.for_user(user)) for user in self.users]
        self.mode = MatchMode.objects.create(key="lan-quick", title="شروع سریع")

    def socket(self, origin, token):
        app = AllowedHostsOriginValidator(JWTAuthMiddleware(URLRouter(websocket_urlpatterns)))
        return ApplicationCommunicator(app, {
            "type": "websocket", "path": "/ws/", "raw_path": b"/ws/", "query_string": b"",
            "headers": [(b"origin", origin.encode())], "subprotocols": ["ft.jwt", token],
            "scheme": "ws", "server": ("backend", 8000), "client": ("127.0.0.1", 12345),
        })

    async def event(self, client, expected):
        for _ in range(12):
            frame = await client.receive_output(timeout=4)
            if frame["type"] == "websocket.send":
                event = json.loads(frame["text"])
                if event["type"] == expected:
                    return event["data"]
        self.fail(f"Missing event {expected}")

    @patch("apps.chat.presence.mark_app_online")
    @patch("apps.chat.presence.mark_app_offline")
    async def test_allowed_network_clients_match_and_exchange_messages(self, offline, online):
        hosts = [host for host in settings.ALLOWED_HOSTS if host not in ("localhost", "127.0.0.1", "backend", "*")]
        origin = f"http://{hosts[-1] if hosts else 'localhost'}:5173"
        clients = [self.socket(origin, self.tokens[0]), self.socket("http://localhost:5173", self.tokens[1])]
        try:
            for client in clients:
                await client.send_input({"type": "websocket.connect"})
                handshake = await client.receive_output(timeout=4)
                self.assertEqual(handshake["type"], "websocket.accept")
                self.assertEqual(handshake["subprotocol"], "ft.jwt")
                await self.event(client, "ready")
            for user in self.users:
                await database_sync_to_async(services.enqueue)(user, self.mode.key)
            await database_sync_to_async(services._match_once)()
            matches = [await self.event(client, "mm.matched") for client in clients]
            self.assertEqual(matches[0]["conversation_id"], matches[1]["conversation_id"])
            conversation_id = matches[0]["conversation_id"]
            for index, sender in enumerate(clients):
                body = f"سلام از بازیکن {index}"
                await sender.send_input({"type": "websocket.receive", "text": json.dumps({"type": "chat.send", "data": {"conversation_id": conversation_id, "body": body, "client_id": f"lan-message-{index}"}})})
                for client in clients:
                    message = await self.event(client, "chat.message")
                    self.assertEqual(message["body"], body)
                    self.assertEqual(message["sender"]["id"], self.users[index].pk)
        finally:
            for client in clients:
                await client.send_input({"type": "websocket.disconnect", "code": 1000})
                await client.wait(timeout=4)

    async def test_unlisted_origin_remains_rejected(self):
        client = self.socket("http://untrusted.example:5173", self.tokens[0])
        await client.send_input({"type": "websocket.connect"})
        response = await client.receive_output(timeout=4)
        self.assertEqual(response["type"], "websocket.close")
        await client.send_input({"type": "websocket.disconnect", "code": 1000})
        await client.wait(timeout=4)
