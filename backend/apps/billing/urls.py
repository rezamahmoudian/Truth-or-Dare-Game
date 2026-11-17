from django.urls import path
from . import views
from . import item_views
from . import reward_views

urlpatterns = [
    path("rewards/", reward_views.RewardStatusView.as_view()),
    path("rewards/callback/<slug:provider_key>/", reward_views.RewardCallbackView.as_view()),
    path("inventory/", item_views.InventoryView.as_view()),
    path("inventory/equip/", item_views.EquipView.as_view()),
    path("inventory/use/", item_views.UseItemView.as_view()),
    path("gift-leaders/", item_views.GiftLeadersView.as_view()),
    path("vip/", views.VIPView.as_view(), name="billing-vip"),
    path("vip/spotlight/", views.SpotlightView.as_view(), name="billing-spotlight"),
    path("catalog/", views.CatalogView.as_view(), name="billing-catalog"),
    path("wallet/", views.WalletView.as_view(), name="billing-wallet"),
    path("entitlements/", views.EntitlementsView.as_view(), name="billing-entitlements"),
    path("ledger/", views.LedgerView.as_view(), name="billing-ledger"),
    path("orders/", views.OrdersView.as_view(), name="billing-orders"),
    path("orders/<uuid:pk>/", views.OrderDetailView.as_view(), name="billing-order-detail"),
    path("orders/<uuid:pk>/payment/", views.StartPaymentView.as_view(), name="billing-payment-start"),
    path("orders/<uuid:pk>/check/", views.CheckPaymentView.as_view(), name="billing-payment-check"),
    path("callback/<uuid:key>/", views.PaymentCallbackView.as_view(), name="billing-payment-callback"),
]
