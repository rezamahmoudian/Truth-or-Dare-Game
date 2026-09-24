from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat import services
from apps.chat.models import Conversation
from apps.chat.payloads import conversation_payload, message_payload
from apps.core.errors import DomainError


def _int_param(request, name: str) -> int | None:
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise DomainError("bad_cursor", f"مقدار {name} نامعتبر است.") from exc


def _require_conversation(conversation_id) -> Conversation:
    conversation = Conversation.objects.filter(pk=conversation_id).first()
    if conversation is None:
        raise DomainError("conversation_not_found", "گفتگو پیدا نشد.", 404)
    return conversation


class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        conversations = services.conversations_for(request.user, with_participants=True)
        return Response(
            [
                conversation_payload(
                    conversation,
                    unread_count=conversation.unread_count,
                    # From the prefetch, not a query per row.
                    participants=[
                        member.user
                        for member in conversation.active_members
                        if member.user_id != request.user.pk
                    ],
                )
                for conversation in conversations
            ]
        )


class RoomCreateView(APIView):
    """Create a room and get its join code.

    Join-by-code exists before matchmaking does because it is the only way to
    test a real multi-device game — and it stays afterwards, since sharing a
    code with friends is the cheapest growth loop this product has.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        conversation = services.create_room(
            request.user, int(request.data.get("max_players") or 8)
        )
        return Response(
            conversation_payload(conversation, participants=[request.user]),
            status=status.HTTP_201_CREATED,
        )


class RoomJoinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        code = str(request.data.get("code") or "")
        if not code:
            raise DomainError("code_required", "کد روم را وارد کنید.")

        conversation, joined = services.join_by_code(request.user, code)
        return Response(
            conversation_payload(
                conversation,
                participants=services.participants_of(conversation.id),
            ),
            status=status.HTTP_201_CREATED if joined else status.HTTP_200_OK,
        )


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id) -> Response:
        participant = services.active_participant(request.user, conversation_id)
        return Response(
            conversation_payload(
                participant.conversation,
                participants=services.participants_of(conversation_id),
            )
        )


class MessageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id) -> Response:
        participant = services.active_participant(request.user, conversation_id)
        messages = services.history(
            participant.conversation,
            before=_int_param(request, "before"),
            after=_int_param(request, "after"),
            limit=_int_param(request, "limit") or 50,
            cleared_before_id=participant.cleared_before_id,
        )
        return Response([message_payload(message) for message in messages])

    def post(self, request, conversation_id) -> Response:
        """HTTP fallback for sending.

        The socket is the normal path; this exists so a message is not lost
        when the connection is down, and so tests can drive chat without a
        WebSocket client.
        """
        participant = services.active_participant(request.user, conversation_id)
        message, created = services.post_message(
            conversation=participant.conversation,
            sender=request.user,
            body=request.data.get("body", ""),
            client_id=str(request.data.get("client_id") or "")[:40],
            reply_to_id=request.data.get("reply_to_id"),
        )
        return Response(
            message_payload(message),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id) -> Response:
        up_to = services.mark_read(
            request.user, conversation_id, int(request.data.get("up_to_message_id") or 0)
        )
        return Response({"up_to_message_id": up_to})


class CloseRoomView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id) -> Response:
        conversation = _require_conversation(conversation_id)
        services.close_room(request.user, conversation)
        return Response(
            conversation_payload(
                conversation, participants=services.participants_of(conversation_id)
            )
        )


class LeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id) -> Response:
        conversation = _require_conversation(conversation_id)
        services.leave(request.user, conversation)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeleteConversationView(APIView):
    """Remove a conversation from the caller's chat list.

    Per person, never for everyone: the other side keeps the room and every
    message in it.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, conversation_id) -> Response:
        conversation = _require_conversation(conversation_id)
        services.delete_for_me(request.user, conversation)
        return Response(status=status.HTTP_204_NO_CONTENT)
