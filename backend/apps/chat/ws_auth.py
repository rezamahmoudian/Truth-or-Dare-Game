"""JWT authentication for WebSocket connections.

The browser WebSocket API cannot set an Authorization header, so the token has
to travel some other way. It is read from the `Sec-WebSocket-Protocol` header
in preference to the query string: query strings end up in access logs, proxy
logs and error reports, and this token is a live credential.

The query-string form is still accepted because command-line clients and load
tests need a way in, but production access logs should strip it.
"""

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.users.models import User

SUBPROTOCOL = "ft.jwt"


@database_sync_to_async
def _user_from_token(raw_token: str):
    try:
        token = AccessToken(raw_token)
    except (InvalidToken, TokenError):
        return AnonymousUser()
    return User.objects.filter(pk=token.get("user_id"), is_active=True).first() or AnonymousUser()


def _extract_token(scope) -> str | None:
    subprotocols = scope.get("subprotocols") or []
    if len(subprotocols) >= 2 and subprotocols[0] == SUBPROTOCOL:
        return subprotocols[1]

    query = scope.get("query_string", b"").decode()
    for part in query.split("&"):
        key, _, value = part.partition("=")
        if key == "token" and value:
            return value

    return None


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        token = _extract_token(scope)
        scope["user"] = await _user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
