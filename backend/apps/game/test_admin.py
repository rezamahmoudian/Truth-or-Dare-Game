from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from apps.game.models import Prompt, PromptReviewStatus, PromptSource, PromptType


class PromptReviewAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username="review-admin", password="test-password"
        )
        self.user = user_model.objects.create_user(
            username="submitter", password="test-password"
        )
        self.prompt = Prompt.objects.create(
            text="یک سؤال اولیه برای بررسی در بازی",
            type=PromptType.TRUTH,
            source=PromptSource.SEED,
            review_status=PromptReviewStatus.PENDING,
            is_active=True,
        )
        self.url = reverse("admin:game_prompt_review")

    def test_queue_shows_existing_prompts_and_requires_admin(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.prompt.text)
        self.assertContains(response, "بانک اولیهٔ بازی")
        self.assertContains(
            self.client.get(reverse("admin:game_prompt_changelist")),
            "صف بررسی و تأیید سؤال‌ها",
        )

    def test_changelist_buttons_update_one_prompt_and_keep_filter(self):
        self.client.force_login(self.admin)
        list_url = reverse("admin:game_prompt_changelist")
        quick_url = reverse("admin:game_prompt_quick_review")
        response = self.client.get(list_url)
        self.assertContains(response, 'id="prompt-quick-review-form"')
        self.assertContains(response, f'value="APPROVED:{self.prompt.pk}"')
        self.assertContains(response, f'value="REJECTED:{self.prompt.pk}"')

        response = self.client.post(
            quick_url,
            {
                "review_action": f"APPROVED:{self.prompt.pk}",
                "return_to": f"{list_url}?review_status__exact=PENDING",
            },
        )
        self.assertRedirects(
            response,
            f"{list_url}?review_status__exact=PENDING",
            fetch_redirect_response=False,
        )
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.review_status, PromptReviewStatus.APPROVED)
        self.assertTrue(self.prompt.is_active)

        response = self.client.post(
            quick_url,
            {"review_action": f"REJECTED:{self.prompt.pk}", "return_to": "//evil.example"},
        )
        self.assertRedirects(response, list_url, fetch_redirect_response=False)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.review_status, PromptReviewStatus.REJECTED)
        self.assertFalse(self.prompt.is_active)

    def test_quick_review_requires_post_and_admin_change_permission(self):
        url = reverse("admin:game_prompt_quick_review")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(url, {"review_action": f"APPROVED:{self.prompt.pk}"}).status_code,
            302,
        )
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.review_status, PromptReviewStatus.PENDING)

    def test_category_is_saved_with_decision_for_only_selected_row(self):
        self.client.force_login(self.admin)
        other = Prompt.objects.create(text="سؤال دیگر", type=PromptType.TRUTH)
        list_response = self.client.get(reverse("admin:game_prompt_changelist"))
        self.assertContains(list_response, f'name="category_{self.prompt.pk}"')
        for decision, category in [("APPROVED", "DEEP"), ("REJECTED", "BOLD")]:
            self.client.post(reverse("admin:game_prompt_quick_review"), {
                "review_action": f"{decision}:{self.prompt.pk}",
                f"category_{self.prompt.pk}": category,
                f"category_{other.pk}": "FUNNY",
            })
            self.prompt.refresh_from_db()
            other.refresh_from_db()
            self.assertEqual(self.prompt.category, category)
            self.assertEqual(self.prompt.review_status, decision)
            self.assertEqual(self.prompt.is_active, decision == "APPROVED")
            self.assertEqual(other.category, "FRIENDLY")

    def test_category_only_save_and_invalid_category_are_atomic(self):
        self.client.force_login(self.admin)
        url = reverse("admin:game_prompt_quick_review")
        self.client.post(url, {"review_action": f"CATEGORY:{self.prompt.pk}", f"category_{self.prompt.pk}": "FUNNY"})
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.category, "FUNNY")
        self.assertEqual(self.prompt.review_status, "PENDING")
        self.assertIsNone(self.prompt.reviewed_at)
        self.client.post(url, {"review_action": f"APPROVED:{self.prompt.pk}", f"category_{self.prompt.pk}": "INVALID"})
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.category, "FUNNY")
        self.assertEqual(self.prompt.review_status, "PENDING")

    def test_review_queue_updates_category_and_rejects_invalid_category(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"prompt_id": self.prompt.pk, "decision": "APPROVED", "prompt_category": "DEEP"})
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.category, "DEEP")
        self.client.post(self.url, {"prompt_id": self.prompt.pk, "decision": "REJECTED", "prompt_category": "INVALID"})
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.review_status, "APPROVED")
        self.assertEqual(self.prompt.category, "DEEP")

    def test_view_only_staff_cannot_edit_category(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.user.user_permissions.add(Permission.objects.get(codename="view_prompt"))
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:game_prompt_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'name="category_{self.prompt.pk}"')
        response = self.client.post(reverse("admin:game_prompt_quick_review"), {
            "review_action": f"CATEGORY:{self.prompt.pk}", f"category_{self.prompt.pk}": "DEEP",
        })
        self.assertEqual(response.status_code, 403)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.category, "FRIENDLY")

    def test_quick_review_form_accepts_valid_csrf_token(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.admin)
        browser.get(reverse("admin:game_prompt_changelist"))
        response = browser.post(
            reverse("admin:game_prompt_quick_review"),
            {
                "review_action": f"APPROVED:{self.prompt.pk}",
                "csrfmiddlewaretoken": browser.cookies["csrftoken"].value,
            },
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(response.status_code, 302)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.review_status, PromptReviewStatus.APPROVED)

    def test_approve_and_reject_keep_activity_in_sync(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            {"prompt_id": self.prompt.pk, "decision": PromptReviewStatus.APPROVED},
        )
        self.assertEqual(response.status_code, 302)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.review_status, PromptReviewStatus.APPROVED)
        self.assertTrue(self.prompt.is_active)
        self.assertEqual(self.prompt.reviewed_by, self.admin)
        self.assertIsNotNone(self.prompt.reviewed_at)

        response = self.client.post(
            self.url,
            {
                "prompt_id": self.prompt.pk,
                "decision": PromptReviewStatus.REJECTED,
                "review_note": "نیاز به بازنویسی",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.review_status, PromptReviewStatus.REJECTED)
        self.assertFalse(self.prompt.is_active)
        self.assertEqual(self.prompt.review_note, "نیاز به بازنویسی")

    def test_filters_and_invalid_decision(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"source": "USER"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.prompt.text)
        self.client.post(
            self.url, {"prompt_id": self.prompt.pk, "decision": "UNKNOWN"}
        )
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.review_status, PromptReviewStatus.PENDING)

    def test_new_admin_prompt_waits_for_review(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:game_prompt_add"),
            {
                "text": "سؤال تازه توسط مدیر برای بررسی",
                "type": PromptType.TRUTH,
                "category": "FRIENDLY",
                "intensity": 1,
                "min_players": 2,
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        prompt = Prompt.objects.get(text="سؤال تازه توسط مدیر برای بررسی")
        self.assertEqual(prompt.review_status, PromptReviewStatus.PENDING)
        self.assertFalse(prompt.is_active)
