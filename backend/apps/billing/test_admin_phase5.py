from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import Permission
from django.core import signing
from uuid import uuid4

from .admin_views import CONFIRM_SALT
from .models import SupportOperation, Wallet

from .tests import Fixtures


@override_settings(BILLING_ORDERS_ENABLED=True)
class PhaseFiveAdminTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)

    def test_dashboard_and_support_pages_render(self):
        dashboard = self.client.get(reverse("admin:billing_order_dashboard"))
        support = self.client.get(reverse("admin:billing_order_support"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "داشبورد مالی")
        self.assertEqual(support.status_code, 200)
        self.assertContains(support, "عملیات پشتیبانی مالی")

    def test_support_post_uses_csrf_protected_admin_route_and_audit(self):
        page = self.client.get(reverse("admin:billing_order_support"))
        token = page.cookies["csrftoken"].value
        response = self.client.post(reverse("admin:billing_order_support"), {
            "action": "grant", "target": self.user.username, "amount": "2",
            "reason": "جبران اختلال", "idempotency_key": str(uuid4()), "csrfmiddlewaretoken": token,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "بررسی پیش از ثبت")
        self.assertFalse(Wallet.objects.filter(user=self.user).exists())
        confirmation = response.context["confirmation"]
        for _ in range(2):
            response = self.client.post(reverse("admin:billing_order_support"), {
                "confirmation": confirmation, "csrfmiddlewaretoken": token,
            })
            self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.credit_wallet.balance, 2)
        self.assertEqual(SupportOperation.objects.count(), 1)

    def test_csrf_missing_never_changes_credit(self):
        response = self.client.post(reverse("admin:billing_order_support"), {
            "action": "grant", "target": self.user.username, "amount": 2,
            "reason": "test", "idempotency_key": str(uuid4()),
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Wallet.objects.exists())

    def test_view_only_staff_cannot_use_support(self):
        self.other.is_staff = True
        self.other.save()
        self.other.user_permissions.add(Permission.objects.get(codename="view_finance_dashboard"))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("admin:billing_order_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:billing_order_support")).status_code, 403)

    def test_grant_operator_does_not_need_global_reporting_access(self):
        self.other.is_staff = True
        self.other.save()
        self.other.user_permissions.add(Permission.objects.get(codename="adjust_wallet"))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("admin:billing_order_support")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:billing_order_support"), {"action": "debit"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:billing_order_dashboard")).status_code, 403)

    def test_confirmation_signature_and_actor_are_checked(self):
        url = reverse("admin:billing_order_support")
        self.client.get(url)
        csrf = self.client.cookies["csrftoken"].value
        data = {"action": "grant", "target": self.user.username, "amount": 2, "reason": "test",
                "idempotency_key": str(uuid4()), "actor_id": self.other.pk}
        confirmation = signing.dumps(data, salt=CONFIRM_SALT)
        self.assertEqual(self.client.post(url, {"csrfmiddlewaretoken": csrf, "confirmation": confirmation}).status_code, 403)
        data["actor_id"] = self.admin.pk
        confirmation = signing.dumps(data, salt=CONFIRM_SALT) + "tamper"
        self.assertEqual(self.client.post(url, {"csrfmiddlewaretoken": csrf, "confirmation": confirmation}).status_code, 302)
        self.assertFalse(SupportOperation.objects.exists())

    def test_dashboard_receipts_and_user_filters(self):
        order = self.purchased()
        self.product.title = "new-title"
        self.product.save()
        response = self.client.get(reverse("admin:billing_order_dashboard"), {"username": self.user.username})
        cards = response.context["cards"]
        self.assertEqual(cards[2]["value"], order.amount)
        self.assertContains(response, order.product_snapshot["title"])
        self.assertNotContains(response, "new-title")
        self.assertEqual(response.context["found_user"], self.user)
        for name, query in [
            ("order", {"user__id__exact": self.user.pk}),
            ("vipsubscription", {"user__id__exact": self.user.pk}),
            ("entitlement", {"wallet__user__id__exact": self.user.pk}),
        ]:
            self.assertEqual(self.client.get(reverse(f"admin:billing_{name}_changelist"), query).status_code, 200)
