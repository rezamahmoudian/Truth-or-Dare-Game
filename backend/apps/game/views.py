from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat import services as chat_services
from apps.game import services
from apps.game.models import Category, Prompt, PromptReviewStatus, PromptType
from apps.moderation.filters import screen


class PromptSuggestionSerializer(serializers.ModelSerializer):
    """The user-facing write shape for a prompt awaiting moderation."""

    class Meta:
        model = Prompt
        fields = ("id", "text", "type", "category", "intensity", "min_players", "review_status", "created_at")
        read_only_fields = ("id", "review_status", "created_at")

    def validate_text(self, value: str) -> str:
        value = value.strip()
        if len(value) < 8:
            raise serializers.ValidationError("سؤال خیلی کوتاه است.")
        if len(value) > 500:
            raise serializers.ValidationError("سؤال نباید بیشتر از ۵۰۰ کاراکتر باشد.")
        result = screen(value)
        if result.blocked:
            raise serializers.ValidationError("این سؤال قابل ارسال نیست.")
        if Prompt.objects.filter(text=result.text).exists():
            raise serializers.ValidationError("این سؤال قبلاً پیشنهاد شده است.")
        return result.text

    def validate_type(self, value: str) -> str:
        if value not in PromptType.values:
            raise serializers.ValidationError("نوع سؤال نامعتبر است.")
        return value

    def validate_category(self, value: str) -> str:
        if value not in Category.values:
            raise serializers.ValidationError("دسته‌بندی نامعتبر است.")
        return value

    def validate_intensity(self, value: int) -> int:
        if value not in (1, 2, 3):
            raise serializers.ValidationError("شدت سؤال باید بین ۱ تا ۳ باشد.")
        return value

    def validate_min_players(self, value: int) -> int:
        if value < 2 or value > 8:
            raise serializers.ValidationError("تعداد بازیکن باید بین ۲ تا ۸ باشد.")
        return value

    def create(self, validated_data):
        return Prompt.objects.create(
            **validated_data,
            source="USER",
            submitted_by=self.context["request"].user,
            review_status=PromptReviewStatus.PENDING,
            is_active=False,
        )


class PromptSuggestionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def get(self, request) -> Response:
        rows = Prompt.objects.filter(
            submitted_by=request.user, source="USER"
        ).order_by("-created_at")
        return Response(PromptSuggestionSerializer(rows, many=True).data)

    def post(self, request) -> Response:
        serializer = PromptSuggestionSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        prompt = serializer.save()
        return Response(
            PromptSuggestionSerializer(prompt).data,
            status=status.HTTP_201_CREATED,
        )


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
            Prompt.objects.filter(
                is_active=True, review_status=PromptReviewStatus.APPROVED
            )
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
