from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_players.models import AISettings
from apps.core.errors import DomainError
from apps.matchmaking import services
from apps.matchmaking.models import MatchMode
from apps.matchmaking.payloads import mode_payload, ticket_payload
from apps.users.payloads import person_payload


class ModeListView(APIView):
    """The home screen's contents.

    Returned from the database so a new mode is a row, not an app release.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response(_modes_for(request.user))


def _modes_for(user) -> list[dict]:
    sizes = services.queue_sizes()
    return [
        mode_payload(
            mode,
            remaining=services.remaining_today(user, mode),
            queue_size=0 if mode.is_ai else sizes.get((mode.size_min, mode.size_max), 0),
        )
        for mode in MatchMode.objects.filter(is_active=True)
    ]


class LobbyView(APIView):
    """Everything the home screen needs, in one call.

    The screen shows modes, queue health, an online count and a row of people
    who are around — four requests on the most-opened screen in the app, or
    one.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response(
            {
                "modes": _modes_for(request.user),
                "ai_settings": AISettings.load().public_payload(),
                "online_count": services.online_count(),
                "active_people": [
                    person_payload(user) for user in services.recently_active(request.user)
                ],
            }
        )


class MatchView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "match"

    def get(self, request) -> Response:
        return Response(services.status(request.user) or {"state": "IDLE"})

    def post(self, request) -> Response:
        mode_key = str(request.data.get("mode") or "")
        if not mode_key:
            raise DomainError("mode_required", "حالت بازی را انتخاب کنید.")
        if MatchMode.objects.filter(key=mode_key, is_ai=True).exists() and request.data.get("ai_consent") is not True:
            raise DomainError("ai_consent_required", "بازی با شخصیت هوش مصنوعی و ارسال متن گفتگو به OpenAI را تأیید کن.", 400)

        ticket = services.enqueue(request.user, mode_key, ai_consent=request.data.get("ai_consent") is True)
        return Response(
            ticket_payload(ticket), status=status.HTTP_201_CREATED
        )

    def delete(self, request) -> Response:
        services.cancel(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
