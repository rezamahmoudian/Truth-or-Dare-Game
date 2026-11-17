from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from . import items


class ItemAction(serializers.Serializer):
    grant_id = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=100)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    recipient_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class InventoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(items.inventory(request.user))


class EquipView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def post(self, request):
        class Input(serializers.Serializer):
            slot = serializers.ChoiceField(choices=sorted(items.EQUIPPABLE))
            grant_id = serializers.IntegerField(min_value=1, allow_null=True)
        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(items.equip(request.user, **data.validated_data))


class UseItemView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "profile"

    def post(self, request):
        data = ItemAction(data=request.data)
        data.is_valid(raise_exception=True)
        args = data.validated_data
        use = items.use_item(request.user, args.pop("grant_id"), args.pop("idempotency_key"), **args)
        from apps.chat.payloads import message_payload
        return Response({"inventory": items.inventory(request.user), "message": message_payload(use.message) if use.message_id else None})


class GiftLeadersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"results": items.leaders(request.user), "period": "calendar_month_utc"})
