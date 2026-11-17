from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Order, PaymentCheckout
from .tests import Fixtures


@override_settings(MONETIZATION_ENABLED=False, BILLING_ORDERS_ENABLED=True)
class MonetizationTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_disabled_commerce_denies_reads_and_mutations(self):
        order = self.order()
        for endpoint in ("catalog/", "wallet/", "vip/", "inventory/", "rewards/", "gift-leaders/"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get('/api/billing/' + endpoint).status_code, 403)
        for endpoint in ("orders/", f"orders/{order.pk}/payment/", "vip/spotlight/", "inventory/equip/", "inventory/use/"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.post('/api/billing/' + endpoint, {}, format='json').status_code, 403)
        self.assertEqual(Order.objects.count(), 1)
        self.assertFalse(PaymentCheckout.objects.exists())

    def test_receipts_and_payment_checks_remain_available(self):
        order = self.order()
        self.assertEqual(self.client.get('/api/billing/orders/').status_code, 200)
        self.assertEqual(self.client.get(f'/api/billing/orders/{order.pk}/').status_code, 200)
        with patch('apps.billing.views.payments.schedule_check') as check:
            response = self.client.post(f'/api/billing/orders/{order.pk}/check/')
        self.assertEqual(response.status_code, 202)
        check.assert_called_once()

    def test_me_exposes_server_flag_but_cannot_change_it(self):
        self.assertIs(self.client.get('/api/users/me/').data['monetization_enabled'], False)
        response = self.client.patch('/api/users/me/', {'monetization_enabled': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.data['monetization_enabled'], False)
        with override_settings(MONETIZATION_ENABLED=True):
            self.assertIs(self.client.get('/api/users/me/').data['monetization_enabled'], True)
            self.assertEqual(self.client.get('/api/billing/catalog/').status_code, 200)
            self.assertEqual(self.client.get('/api/billing/wallet/').status_code, 200)
