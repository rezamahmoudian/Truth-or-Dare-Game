from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .permissions import MonetizationEnabled
from apps.core.errors import DomainError
from . import rewards


class RewardStatusView(APIView):
    permission_classes = [IsAuthenticated, MonetizationEnabled]
    throttle_scope = "profile"

    def get(self, request):
        return Response(rewards.status())

    def post(self, request):
        session = rewards.start(request.user)
        _, adapter = rewards.provider()
        return Response({"session_id": session.pk, "expires_at": session.expires_at, "launch": adapter.launch(session)})


class RewardCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "billing_callback"

    def post(self, request, provider_key):
        key, adapter = rewards.provider()
        if not adapter or provider_key != key:
            raise DomainError("ads_unavailable", "سرویس فعال نیست.", 503)
        proof = adapter.verify_callback(request)
        rewards.grant_verified(key, proof)
        return Response({"received": True})
