from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.services import active_participant
from apps.core.errors import DomainError
from apps.users.payloads import person_payload

from . import services
from .models import AIConversation, AISettings


class PersonaListView(APIView):
    def get(self, request):
        return Response({"available": services.available(), "settings": AISettings.load().public_payload(), "personas": [
            person_payload(p.user) for p in services.eligible_personas(request.user).order_by("id")
        ]})


class RetryView(APIView):
    throttle_scope = "ai_retry"

    def post(self, request, conversation_id):
        active_participant(request.user, conversation_id)
        services.assert_available(request.user)
        state = AIConversation.objects.filter(pk=conversation_id, human=request.user).first()
        if state is None or not services.valid(state):
            raise DomainError("ai_unavailable", "این گفتگوی هوش مصنوعی فعال نیست.", 409)
        services.notify(conversation_id)
        return Response({"queued": True}, status=202)
