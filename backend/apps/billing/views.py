from django.conf import settings
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponseRedirect
from rest_framework import serializers
from rest_framework.permissions import AllowAny

from .permissions import MonetizationEnabled
from . import services
from .models import Entitlement, Order, WalletLedger
from .serializers import CreateOrderSerializer, EntitlementSerializer, LedgerSerializer, OrderSerializer
from .wallets import wallet_snapshot
from . import payments
from .gateways import payments_enabled, public_origin
from .models import PaymentCheckout


class BillingPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class CatalogView(APIView):
    permission_classes = [IsAuthenticated, MonetizationEnabled]

    def get(self, request):
        offers = services.available_offers().filter(channel="web")
        from .vip import active_period, benefits, price_for
        period = active_period(request.user.pk)
        from .models import Product, DigitalItem
        from .items import snapshot
        from django.db.models import Count, Q
        item_rows = DigitalItem.objects.select_related("product").annotate(approved_prompt_count=Count("prompts", filter=Q(prompts__is_active=True, prompts__review_status="APPROVED"))).order_by("product__sort_order", "pk")
        item_data = {item.product_id: snapshot(item) for item in item_rows}
        vip_product = Product.objects.filter(key="vip-30", kind="VIP").first()
        return Response({"items": [{"product_key": item.product.key, "description": item.product.description, **item_data[item.product_id]} for item in item_rows],
            "vip_preview": {"benefits": benefits(vip_product.benefits if vip_product else {})},
            "orders_enabled": settings.BILLING_ORDERS_ENABLED, "payment_enabled": payments_enabled(), "offers": [
            {"id": offer.pk, "key": offer.key, **price_for(offer, period), "original_amount": offer.original_amount,
             "currency": offer.currency, "starts_at": offer.starts_at, "ends_at": offer.ends_at,
             "product": {"key": offer.product.key, "title": offer.product.title, "description": offer.product.description,
                         "kind": offer.product.kind, "credits": offer.product.credits, "duration_days": offer.product.duration_days,
                         "item": item_data.get(offer.product_id),
                         "credit_validity_days": offer.product.credit_validity_days, "benefits": benefits(offer.product.benefits) if offer.product.kind == "VIP" else offer.product.benefits}}
            for offer in offers
        ]})


class VIPView(APIView):
    permission_classes = [IsAuthenticated, MonetizationEnabled]

    def get(self, request):
        from .vip import membership
        return Response(membership(request.user))


class SpotlightView(APIView):
    permission_classes = [IsAuthenticated, MonetizationEnabled]
    throttle_scope = "profile"

    def post(self, request):
        if not isinstance(request.data, dict) or set(request.data) != {"idempotency_key"}:
            raise serializers.ValidationError("فقط شناسه درخواست را ارسال کن.")
        from .vip import activate_spotlight, membership
        activate_spotlight(user=request.user, idempotency_key=request.data["idempotency_key"])
        return Response(membership(request.user))


class WalletView(APIView):
    permission_classes = [IsAuthenticated, MonetizationEnabled]

    def get(self, request):
        return Response(wallet_snapshot(request.user))


class OrdersView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method == "POST":
            permissions.append(MonetizationEnabled())
        return permissions
    serializer_class = OrderSerializer
    pagination_class = BillingPagination

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def get_throttles(self):
        self.throttle_scope = "billing_order" if self.request.method == "POST" else None
        return super().get_throttles()

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.create_order(user=request.user, **serializer.validated_data)
        # Same status/body on replay; never start a payment from this endpoint.
        return Response(OrderSerializer(order).data, status=200)


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        return Response({**OrderSerializer(order).data, "payment": payments.payment_payload(order)})


class StartPaymentView(APIView):
    permission_classes = [IsAuthenticated, MonetizationEnabled]
    throttle_scope = "billing_payment"

    def post(self, request, pk):
        if not isinstance(request.data, dict) or set(request.data) != {"idempotency_key"}:
            raise serializers.ValidationError("فقط شناسهٔ درخواست را ارسال کن.")
        return Response(payments.begin_payment(user=request.user, order_id=pk,
            idempotency_key=request.data.get("idempotency_key")))


class CheckPaymentView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "billing_check"

    def post(self, request, pk):
        from django.shortcuts import get_object_or_404
        order = get_object_or_404(Order, pk=pk, user=request.user)
        payments.schedule_check(order)
        return Response(payments.payment_payload(order), status=202)


class PaymentCallbackView(APIView):
    # The browser returning from a bank has no bearer token. This route only
    # schedules trusted verification; arbitrary GET/POST fields are ignored.
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "billing_callback"

    def get(self, request, key):
        from django.shortcuts import get_object_or_404
        checkout = get_object_or_404(PaymentCheckout.objects.select_related("attempt__order"), callback_key=key)
        origin = public_origin()
        payments.schedule_check(checkout.attempt.order)
        response = HttpResponseRedirect(f"{origin}/shop/payment/{checkout.attempt.order_id}")
        response.status_code = 303
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def post(self, request, key):
        return self.get(request, key)


class EntitlementsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntitlementSerializer
    pagination_class = BillingPagination

    def get_queryset(self):
        wallet_snapshot(self.request.user)
        return Entitlement.objects.filter(wallet__user=self.request.user).order_by("-id")


class LedgerView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LedgerSerializer
    pagination_class = BillingPagination

    def get_queryset(self):
        wallet_snapshot(self.request.user)
        return WalletLedger.objects.filter(wallet__user=self.request.user)
