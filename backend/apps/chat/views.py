from django.db import transaction
from django.http import FileResponse
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat import services
from apps.chat.attachments import inspect_upload, private_storage
from apps.chat.models import Conversation, Message, MessageType
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


class AttachmentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "chat_upload"

    def post(self, request, conversation_id):
        services.active_participant(request.user, conversation_id)
        upload = request.FILES.get("file")
        client_id = str(request.data.get("client_id", ""))
        if not upload or not client_id or len(client_id) > 40:
            raise DomainError("invalid_upload", "فایل و شناسهٔ ارسال معتبر لازم است.")
        name, info = inspect_upload(upload, request.data.get("voice") == "true")
        storage = private_storage()
        saved_name = None
        try:
            with transaction.atomic():
                conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
                services.active_participant(request.user, conversation_id)
                existing = Message.objects.filter(conversation=conversation, client_id=client_id).first()
                if existing:
                    if existing.sender_id != request.user.pk:
                        raise DomainError("client_id_conflict", "شناسهٔ ارسال تکراری است.", 409)
                    return Response(message_payload(existing))
                saved_name = storage.save(name, upload)
                message, created = services.post_message(
                    conversation=conversation,
                    sender=request.user,
                    body=str(request.data.get("body", "")),
                    client_id=client_id,
                    message_type=MessageType.ATTACHMENT,
                    attachment_name=saved_name,
                    attachment_info=info,
                )
                if not created:
                    storage.delete(saved_name)
                    saved_name = None
        except Exception:
            # Storage is outside the DB transaction; clean up failed uploads.
            if saved_name and not Message.objects.filter(attachment=saved_name).exists():
                storage.delete(saved_name)
            raise
        return Response(message_payload(message), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AttachmentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id, message_id):
        participant = services.active_participant(request.user, conversation_id)
        message = Message.objects.filter(
            pk=message_id, conversation_id=conversation_id,
            id__gt=participant.cleared_before_id, is_deleted=False,
        ).first()
        if not message or not message.attachment:
            raise DomainError("file_not_found", "فایل پیدا نشد.", 404)
        try:
            file = private_storage().open(message.attachment.name, "rb")
        except FileNotFoundError as exc:
            raise DomainError("file_not_found", "فایل در دسترس نیست.", 404) from exc
        response = FileResponse(
            file, as_attachment=True,
            filename=message.attachment_info.get("name", "file"),
            content_type=message.attachment_info.get("mime", "application/octet-stream"),
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return response


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
