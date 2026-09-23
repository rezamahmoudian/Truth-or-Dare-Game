from django.urls import path

from apps.chat.consumers import AppConsumer

# One route. The architecture calls for a single socket carrying every
# conversation, so there is deliberately no per-room endpoint here.
websocket_urlpatterns = [
    path("ws/", AppConsumer.as_asgi()),
]
