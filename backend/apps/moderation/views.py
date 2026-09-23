from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.payloads import message_payload
from apps.core.errors import DomainError
from apps.moderation import services
from apps.users.models import ReportReason
from apps.users.payloads import person_payload


class ReasonListView(APIView):
    """The report reasons, from the model's own choices.

    Sent to the client rather than hardcoded there so the two can never drift
    into offering a reason the server will reject.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response(
            [{"key": key, "label": label} for key, label in ReportReason.choices]
        )


class ReportView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def post(self, request) -> Response:
        target = request.data.get("target_user_id")
        if not target:
            raise DomainError("target_required", "کاربر مورد نظر مشخص نیست.")

        services.report(
            request.user,
            int(target),
            str(request.data.get("reason") or ""),
            note=str(request.data.get("note") or ""),
            message_id=request.data.get("message_id"),
        )
        return Response(
            {"detail": "گزارش شما ثبت شد و بررسی می‌شود."},
            status=status.HTTP_201_CREATED,
        )


class BlockListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response(
            [person_payload(user) for user in services.blocked_users(request.user)]
        )


class BlockView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def post(self, request, user_id: int) -> Response:
        services.block(request.user, user_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, user_id: int) -> Response:
        services.unblock(request.user, user_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, message_id: int) -> Response:
        message = services.delete_message(request.user, message_id)
        return Response(message_payload(message))
