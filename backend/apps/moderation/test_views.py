from django.test import TestCase
from rest_framework.test import APIClient

from apps.users.models import User


class ReportInputTests(TestCase):
    def setUp(self):
        self.reporter = User.objects.create_user(username="reporter", display_name="گزارش‌دهنده")
        self.target = User.objects.create_user(username="target", display_name="هدف")
        self.client = APIClient()
        self.client.force_authenticate(self.reporter)

    def test_malformed_ids_return_bad_request_instead_of_server_error(self):
        response = self.client.post(
            "/api/reports/",
            {"target_user_id": "not-an-id", "reason": "OTHER"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_report_target")

        response = self.client.post(
            "/api/reports/",
            {"target_user_id": self.target.pk, "message_id": "bad", "reason": "OTHER"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_report_target")
