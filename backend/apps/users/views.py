import logging

from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.errors import DomainError
from apps.users import social
from apps.users.models import User, hash_device_token
from apps.users.payloads import person_payload, request_payload
from apps.users.serializers import (
    GuestAuthSerializer,
    MeSerializer,
    UpgradeAccountSerializer,
)

logger = logging.getLogger("ft.users")


def issue_tokens(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class GuestAuthView(APIView):
    """Sign in with a device token, creating the account on first contact.

    There is no registration step because the product spreads through shared
    links: someone tapping a friend's game invitation should land in the game,
    not on a signup form. The account becomes recoverable later via /upgrade/.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"

    def post(self, request) -> Response:
        serializer = GuestAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_hash = hash_device_token(serializer.validated_data["device_token"])

        user = User.objects.filter(device_token_hash=token_hash).first()
        created = False

        if user is None:
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=User.generate_username(),
                        device_token_hash=token_hash,
                        is_guest=True,
                    )
                    user.set_unusable_password()
                    user.save(update_fields=["password"])
                created = True
            except IntegrityError:
                # Two launches raced with the same token; the other one won.
                user = User.objects.get(device_token_hash=token_hash)

        if not user.is_active:
            return Response(
                {"detail": "این حساب غیرفعال شده است."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user.touch_last_seen()

        logger.info(
            "auth.guest_created" if created else "auth.guest_resumed",
            extra={"user_id": user.pk, "event": "auth.guest"},
        )

        return Response(
            {
                **issue_tokens(user),
                "created": created,
                "user": MeSerializer(user).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def get_object(self) -> User:
        return self.request.user

    def get_throttles(self):
        # Reading your own profile happens on every app launch; only writes
        # need a budget.
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return []
        return super().get_throttles()


class UpgradeAccountView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request) -> Response:
        if not request.user.is_guest:
            return Response(
                {"detail": "این حساب از قبل دائمی است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = UpgradeAccountSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.username = serializer.validated_data["username"]
        user.set_password(serializer.validated_data["password"])
        user.is_guest = False
        user.save(update_fields=["username", "password", "is_guest"])

        logger.info(
            "auth.account_upgraded",
            extra={"user_id": user.pk, "event": "auth.upgrade"},
        )

        # Rotate: the tokens issued to the guest session stay valid otherwise,
        # and the point of upgrading is that this identity is now worth
        # protecting.
        return Response({**issue_tokens(user), "user": MeSerializer(user).data})


class PublicProfileView(APIView):
    """Someone else's profile, plus where you stand with them.

    The relation travels with the profile because every screen that shows a
    person also has to show the right button — add, accept, cancel or nothing —
    and a second round trip to find out would make that button flicker.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, username: str | None = None, user_id: int | None = None) -> Response:
        lookup = {"username": username} if username else {"pk": user_id}
        other = User.objects.filter(is_active=True, **lookup).first()
        if other is None:
            raise DomainError("user_not_found", "کاربر پیدا نشد.", 404)
        return Response(
            person_payload(other, relation=social.relation_to(request.user, other))
        )


class FriendListView(APIView):
    """Friends and both directions of pending requests, in one call.

    The friends tab needs all three to render; splitting them across endpoints
    would mean three round trips on a screen people open constantly.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response(
            {
                "friends": [
                    person_payload(friend, relation="FRIENDS")
                    for friend in social.friends_of(request.user)
                ],
                "incoming": [
                    request_payload(row, direction="incoming")
                    for row in social.incoming_requests(request.user)
                ],
                "outgoing": [
                    request_payload(row, direction="outgoing")
                    for row in social.outgoing_requests(request.user)
                ],
            }
        )


class FriendRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def post(self, request, user_id: int) -> Response:
        social.send_request(request.user, user_id)
        other = User.objects.get(pk=user_id)
        return Response(
            person_payload(other, relation=social.relation_to(request.user, other)),
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, user_id: int) -> Response:
        social.remove(request.user, user_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FriendAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id: int) -> Response:
        friendship = social.accept_request(request.user, user_id)
        return Response(
            {
                "conversation_id": str(friendship.conversation_id),
                "user": person_payload(
                    friendship.other_than(request.user.pk), relation="FRIENDS"
                ),
            }
        )


class FriendDeclineView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id: int) -> Response:
        social.decline_request(request.user, user_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
