from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat import services as chat_services
from apps.game import services
from apps.game.models import Prompt


class GameStateView(APIView):
    """Current game state for a conversation.

    The socket pushes a snapshot on every transition, but a client that just
    opened the screen — or just reconnected — needs to ask for the current one
    rather than wait for the next change.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id) -> Response:
        chat_services.active_participant(request.user, conversation_id)
        return Response(services.state_of(conversation_id))

    def post(self, request, conversation_id) -> Response:
        participant = chat_services.active_participant(request.user, conversation_id)
        services.start_game(
            request.user,
            participant.conversation,
            category=str(request.data.get("category") or ""),
            max_intensity=int(request.data.get("max_intensity") or 2),
        )
        return Response(
            services.state_of(conversation_id), status=status.HTTP_201_CREATED
        )

    def delete(self, request, conversation_id) -> Response:
        services.stop_game(request.user, conversation_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryListView(APIView):
    """Which categories actually have prompts behind them.

    Offering a category the bank cannot fill produces a game that dies on the
    first turn, so the list is derived from the data rather than hardcoded.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        rows = (
            Prompt.objects.filter(is_active=True)
            .values("category")
            .distinct()
            .order_by("category")
        )
        labels = dict(Prompt._meta.get_field("category").choices)
        return Response(
            [
                {"key": row["category"], "label": labels.get(row["category"], row["category"])}
                for row in rows
            ]
        )
