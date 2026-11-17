from rest_framework import serializers

from .models import Entitlement, Order, WalletLedger


class CreateOrderSerializer(serializers.Serializer):
    offer_id = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=100, trim_whitespace=True)

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        # Neither price, product contents nor another user's identity is client input.
        if set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["فقط شناسهٔ پیشنهاد و شناسهٔ درخواست را ارسال کن."]})
        return validated


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ("id", "offer_id", "product_snapshot", "amount", "currency", "status", "created_at", "expires_at", "paid_at", "fulfilled_at")
        read_only_fields = fields


class EntitlementSerializer(serializers.ModelSerializer):
    available = serializers.SerializerMethodField()

    def get_available(self, obj):
        return obj.remaining - obj.reserved

    class Meta:
        model = Entitlement
        fields = ("id", "order_id", "source", "amount", "remaining", "reserved", "available", "starts_at", "expires_at", "status")
        read_only_fields = fields


class LedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletLedger
        fields = ("id", "entitlement_id", "reservation_id", "kind", "delta", "reserved_delta", "balance_before", "balance_after", "reserved_before", "reserved_after", "reason", "created_at")
        read_only_fields = fields
