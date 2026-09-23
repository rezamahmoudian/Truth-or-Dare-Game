"""The one socket.

A user holds a single connection for the whole app, joined to `user.<id>`,
which carries events for every conversation they belong to. Opening a
conversation screen additionally subscribes to `conv.<uuid>` for typing and
presence — traffic that is never stored and is meaningless to someone who is
not looking at that screen.

One socket per conversation would mean ten friends equals ten sockets on a
phone, ten TLS handshakes on resume, and ten reconnect storms when the network
flaps.
"""

import logging
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.chat import presence, services
from apps.chat.payloads import message_payload
from apps.chat.ws_auth import SUBPROTOCOL
from apps.core.errors import DomainError

logger = logging.getLogger("ft.ws")

# A crude ceiling on how fast one connection may act. Not a substitute for
# moderation — just enough that a stuck client or a bored user cannot saturate
# the channel layer for everyone else in the room.
RATE_WINDOW_SECONDS = 10
RATE_MAX_ACTIONS = 40


class AppConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.user = self.scope.get("user")
        self.subscribed: set[str] = set()
        self._window_start = time.monotonic()
        self._window_count = 0

        offered = self.scope.get("subprotocols") or []
        accepted = SUBPROTOCOL if SUBPROTOCOL in offered else None

        if not self.user or not self.user.is_authenticated:
            # Accept first, then close with 4401. Closing before the handshake
            # completes makes the server answer HTTP 403, which reaches the
            # browser as a bare code 1006 — indistinguishable from a dropped
            # connection. The client would then retry forever with the same
            # expired token instead of refreshing it.
            await self.accept(accepted)
            await self._error("unauthenticated", "نشست معتبر نیست.")
            await self.close(code=4401)
            return

        await self.accept(accepted)
        await self.channel_layer.group_add(f"user.{self.user.pk}", self.channel_name)

        await self.send_json({"type": "ready", "data": {"user_id": self.user.pk}})
        logger.info("ws.connected", extra={"event": "ws.connected", "user_id": self.user.pk})

    async def disconnect(self, code) -> None:
        user = getattr(self, "user", None)
        if not user or not user.is_authenticated:
            return

        for conversation_id in list(getattr(self, "subscribed", ())):
            await self._unsubscribe(conversation_id)

        await self.channel_layer.group_discard(f"user.{user.pk}", self.channel_name)

    # -- inbound ----------------------------------------------------------

    async def receive_json(self, content, **kwargs) -> None:
        action = content.get("type")
        data = content.get("data") or {}

        if action == "ping":
            await self._heartbeat()
            return

        if not self._allow_action():
            await self._error("rate_limited", "سرعت ارسال بیش از حد مجاز است.")
            return

        handlers = {
            "conv.subscribe": self._on_subscribe,
            "conv.unsubscribe": self._on_unsubscribe,
            "conv.close": self._on_close,
            "chat.send": self._on_send,
            "chat.typing": self._on_typing,
            "chat.read": self._on_read,
            "chat.react": self._on_react,
            "game.start": self._on_game_start,
            "game.choose": self._on_game_choose,
            "game.answer": self._on_game_answer,
            "game.skip": self._on_game_skip,
            "game.confirm": self._on_game_confirm,
            "game.force_next": self._on_game_force_next,
            "game.stop": self._on_game_stop,
            "mm.enqueue": self._on_mm_enqueue,
            "mm.cancel": self._on_mm_cancel,
        }
        handler = handlers.get(action)
        if handler is None:
            await self._error("unknown_action", f"دستور ناشناخته: {action}")
            return

        try:
            await handler(data)
        except DomainError as error:
            await self._error(error.code, error.message, data.get("client_id"))
        except Exception:
            logger.exception("ws.handler_failed", extra={"action": action})
            await self._error("server_error", "خطای غیرمنتظره رخ داد.")

    def _allow_action(self) -> bool:
        now = time.monotonic()
        if now - self._window_start > RATE_WINDOW_SECONDS:
            self._window_start = now
            self._window_count = 0
        self._window_count += 1
        return self._window_count <= RATE_MAX_ACTIONS

    async def _heartbeat(self) -> None:
        # Refreshes presence for every open conversation; a client that stops
        # pinging ages out of the online set without needing a clean close.
        for conversation_id in getattr(self, "subscribed", ()):
            await database_sync_to_async(presence.mark_online)(
                conversation_id, self.user.pk
            )
        await self.send_json({"type": "pong", "data": {}})

    # -- handlers ---------------------------------------------------------

    async def _on_subscribe(self, data) -> None:
        conversation_id = str(data.get("conversation_id") or "")
        await database_sync_to_async(services.active_participant)(
            self.user, conversation_id
        )

        await self.channel_layer.group_add(f"conv.{conversation_id}", self.channel_name)
        self.subscribed.add(conversation_id)

        await database_sync_to_async(presence.mark_online)(conversation_id, self.user.pk)
        await self._broadcast_presence(conversation_id)

    async def _on_unsubscribe(self, data) -> None:
        await self._unsubscribe(str(data.get("conversation_id") or ""))

    async def _unsubscribe(self, conversation_id: str) -> None:
        if conversation_id not in self.subscribed:
            return
        await self.channel_layer.group_discard(f"conv.{conversation_id}", self.channel_name)
        self.subscribed.discard(conversation_id)
        await database_sync_to_async(presence.mark_offline)(conversation_id, self.user.pk)
        await self._broadcast_presence(conversation_id)

    async def _on_close(self, data) -> None:
        await database_sync_to_async(self._close_room)(
            str(data.get("conversation_id") or "")
        )

    def _close_room(self, conversation_id: str):
        participant = services.active_participant(self.user, conversation_id)
        return services.close_room(self.user, participant.conversation)

    async def _on_send(self, data) -> None:
        message, created = await database_sync_to_async(self._send_message)(data)
        if not created:
            # A retry of something already stored. The fan-out already happened
            # the first time, so only the sender needs the reconciliation.
            await self.send_json(
                {"type": "chat.message", "data": await self._payload(message)}
            )

    def _send_message(self, data):
        participant = services.active_participant(
            self.user, str(data.get("conversation_id") or "")
        )
        return services.post_message(
            conversation=participant.conversation,
            sender=self.user,
            body=data.get("body", ""),
            client_id=str(data.get("client_id") or "")[:40],
            reply_to_id=data.get("reply_to_id"),
        )

    @database_sync_to_async
    def _payload(self, message) -> dict:
        return message_payload(message)

    async def _on_typing(self, data) -> None:
        conversation_id = str(data.get("conversation_id") or "")
        if conversation_id not in self.subscribed:
            return
        # Straight to the conversation group without touching the database:
        # typing is worthless a second later, and clients expire it themselves.
        await self.channel_layer.group_send(
            f"conv.{conversation_id}",
            {
                "type": "fanout",
                "event": "chat.typing",
                "data": {
                    "conversation_id": conversation_id,
                    "user_id": self.user.pk,
                    "is_typing": bool(data.get("is_typing")),
                },
            },
        )

    async def _on_read(self, data) -> None:
        await database_sync_to_async(services.mark_read)(
            self.user,
            str(data.get("conversation_id") or ""),
            int(data.get("up_to_message_id") or 0),
        )

    async def _on_react(self, data) -> None:
        await database_sync_to_async(services.set_reaction)(
            self.user,
            int(data.get("message_id") or 0),
            str(data.get("emoji") or ""),
            str(data.get("op") or "add"),
        )

    # -- game -------------------------------------------------------------
    #
    # Every one of these goes through apps.game.services, the same functions
    # the REST views call. The socket is a transport, never a second copy of
    # the rules.

    async def _on_game_start(self, data) -> None:
        await database_sync_to_async(self._start_game)(data)

    def _start_game(self, data):
        from apps.game import services as game_services

        participant = services.active_participant(
            self.user, str(data.get("conversation_id") or "")
        )
        return game_services.start_game(
            self.user,
            participant.conversation,
            category=str(data.get("category") or ""),
            max_intensity=int(data.get("max_intensity") or 2),
            rounds=data.get("rounds"),
        )

    async def _on_game_choose(self, data) -> None:
        from apps.game import services as game_services

        await database_sync_to_async(game_services.choose)(
            self.user, int(data.get("turn_id") or 0), str(data.get("choice") or "")
        )

    async def _on_game_answer(self, data) -> None:
        from apps.game import services as game_services

        await database_sync_to_async(game_services.answer)(
            self.user, int(data.get("turn_id") or 0), str(data.get("body") or "")
        )

    async def _on_game_skip(self, data) -> None:
        from apps.game import services as game_services

        await database_sync_to_async(game_services.skip)(
            self.user, int(data.get("turn_id") or 0)
        )

    async def _on_game_confirm(self, data) -> None:
        from apps.game import services as game_services

        await database_sync_to_async(game_services.confirm)(
            self.user, int(data.get("turn_id") or 0)
        )

    async def _on_game_force_next(self, data) -> None:
        from apps.game import services as game_services

        await database_sync_to_async(game_services.force_next)(
            self.user, int(data.get("turn_id") or 0)
        )

    async def _on_game_stop(self, data) -> None:
        from apps.game import services as game_services

        await database_sync_to_async(game_services.stop_game)(
            self.user, str(data.get("conversation_id") or "")
        )

    # -- matchmaking ------------------------------------------------------

    async def _on_mm_enqueue(self, data) -> None:
        from apps.matchmaking import services as match_services

        await database_sync_to_async(match_services.enqueue)(
            self.user, str(data.get("mode") or "")
        )

    async def _on_mm_cancel(self, data) -> None:
        from apps.matchmaking import services as match_services

        await database_sync_to_async(match_services.cancel)(self.user)

    # -- outbound ---------------------------------------------------------

    async def _broadcast_presence(self, conversation_id: str) -> None:
        online = await database_sync_to_async(presence.online_user_ids)(conversation_id)
        await self.channel_layer.group_send(
            f"conv.{conversation_id}",
            {
                "type": "fanout",
                "event": "presence",
                "data": {"conversation_id": conversation_id, "online_user_ids": online},
            },
        )

    async def _error(self, code: str, message: str, client_id: str | None = None) -> None:
        await self.send_json(
            {
                "type": "error",
                "data": {"code": code, "message": message, "client_id": client_id},
            }
        )

    async def fanout(self, event) -> None:
        """Single entry point for everything the channel layer delivers."""
        await self.send_json({"type": event["event"], "data": event["data"]})
