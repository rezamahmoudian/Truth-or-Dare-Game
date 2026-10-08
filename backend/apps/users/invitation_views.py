from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import invitations


class InvitationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(invitations.lists(request.user))


class InvitationSendView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def post(self, request, user_id):
        row = invitations.send(request.user, user_id)
        return Response(invitations.payload(row, request.user.pk), status=201)


class InvitationRespondView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def post(self, request, invitation_id, action):
        row = invitations.respond(request.user, invitation_id, action)
        return Response(invitations.payload(row, request.user.pk))
