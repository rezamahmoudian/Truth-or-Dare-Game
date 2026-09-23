"""
ASGI entrypoint.

The whole project runs under ASGI (not WSGI + a separate socket server) so HTTP
and WebSocket share one process, one settings module and one auth layer.

Ordering matters: `get_asgi_application()` must run before any import that
touches models, otherwise Django raises AppRegistryNotReady.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.chat.ws_auth import JWTAuthMiddleware  # noqa: E402
from config.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # JWT rather than session auth: the app authenticates with tokens, and
        # a session-cookie socket would be a second, divergent auth path.
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)
