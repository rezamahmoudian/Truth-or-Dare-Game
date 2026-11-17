from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from apps.game.models import (
    Category,
    GameSession,
    Prompt,
    PromptFeedbackValue,
    PromptReviewStatus,
    PromptSource,
    PromptType,
    Turn,
)


class NegativeFeedbackFilter(admin.SimpleListFilter):
    title = "بازخورد منفی"
    parameter_name = "negative_feedback"

    def lookups(self, request, model_admin):
        return (
            ("any", "حداقل یک رأی منفی"),
            ("3", "۳ رأی منفی یا بیشتر"),
            ("5", "۵ رأی منفی یا بیشتر"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "any":
            return queryset.filter(negative_feedback_count__gte=1)
        if value in {"3", "5"}:
            return queryset.filter(negative_feedback_count__gte=int(value))
        return queryset


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    """The prompt bank is content, not code — moderators live here.

    Deactivating rather than deleting keeps a prompt out of new games without
    breaking the turns that already referenced it.
    """

    list_display = (
        "full_text",
        "type",
        "category",
        "intensity",
        "source",
        "review_status",
        "is_active",
        "positive_feedback_count",
        "negative_feedback_count",
        "submitted_by",
        "reviewed_at",
        "review_controls",
    )
    list_filter = (
        "pack",
        "review_status",
        "source",
        "type",
        "category",
        "intensity",
        "is_active",
        NegativeFeedbackFilter,
    )
    search_fields = ("text", "submitted_by__username", "submitted_by__display_name")
    readonly_fields = (
        "source",
        "submitted_by",
        "review_status",
        "is_active",
        "reviewed_by",
        "reviewed_at",
        "review_note",
        "created_at",
    )
    actions = ("approve_prompts", "reject_prompts", "deactivate_negative_prompts", "activate_prompts")
    change_list_template = "admin/game/prompt/change_list.html"

    def get_list_display(self, request):
        fields = super().get_list_display(request)
        if not self.has_change_permission(request):
            return fields[:-1]
        return tuple("category_control" if field == "category" else field for field in fields)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            positive_feedback_count=Count(
                "feedbacks", filter=Q(feedbacks__value=PromptFeedbackValue.POSITIVE), distinct=True
            ),
            negative_feedback_count=Count(
                "feedbacks", filter=Q(feedbacks__value=PromptFeedbackValue.NEGATIVE), distinct=True
            ),
        )

    @admin.display(description="👍 مثبت", ordering="positive_feedback_count")
    def positive_feedback_count(self, obj):
        return getattr(obj, "positive_feedback_count", 0)

    @admin.display(description="👎 منفی", ordering="negative_feedback_count")
    def negative_feedback_count(self, obj):
        return getattr(obj, "negative_feedback_count", 0)

    @admin.display(description="دسته‌بندی", ordering="category")
    def category_control(self, obj):
        options = format_html_join(
            "", '<option value="{}"{}>{}</option>',
            ((value, ' selected' if value == obj.category else "", label)
             for value, label in Category.choices),
        )
        return format_html(
            '<select name="category_{}" form="prompt-quick-review-form" '
            'aria-label="دسته‌بندی سؤال {}">{}</select> '
            '<button type="submit" form="prompt-quick-review-form" name="review_action" '
            'value="CATEGORY:{}" class="prompt-review-button save-category">ذخیره دسته</button>',
            obj.pk, obj.pk, options, obj.pk,
        )

    def get_urls(self):
        custom_urls = [
            path(
                "review/",
                self.admin_site.admin_view(self.review_queue),
                name="game_prompt_review",
            ),
            path(
                "quick-review/",
                self.admin_site.admin_view(self.quick_review),
                name="game_prompt_quick_review",
            ),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "review_queue_url": reverse("admin:game_prompt_review"),
            "quick_review_url": reverse("admin:game_prompt_quick_review"),
            "return_to_changelist": request.get_full_path(),
        }
        return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.is_active = False
            obj.review_status = PromptReviewStatus.PENDING
        super().save_model(request, obj, form, change)

    def _set_review_status(self, queryset, decision, reviewer, note="", category=None):
        return queryset.update(
            **({"category": category} if category is not None else {}),
            review_status=decision,
            is_active=decision == PromptReviewStatus.APPROVED,
            reviewed_by=reviewer,
            reviewed_at=timezone.now(),
            review_note="" if decision == PromptReviewStatus.APPROVED else note[:300],
        )

    @admin.action(description="تأیید سؤال‌های انتخاب‌شده و افزودن به بازی")
    def approve_prompts(self, request, queryset):
        updated = self._set_review_status(queryset, PromptReviewStatus.APPROVED, request.user)
        self.message_user(request, f"{updated} سؤال تأیید شد و در بازی قرار گرفت.")

    @admin.action(description="رد سؤال‌های انتخاب‌شده")
    def reject_prompts(self, request, queryset):
        updated = self._set_review_status(queryset, PromptReviewStatus.REJECTED, request.user)
        self.message_user(request, f"{updated} سؤال رد شد.")

    @admin.action(description="غیرفعال‌کردن سؤال‌های دارای بازخورد منفی")
    def deactivate_negative_prompts(self, request, queryset):
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f"{updated} سؤال از انتخاب بازی خارج شد؛ سابقهٔ بررسی آن حفظ شد.")

    @admin.action(description="فعال‌سازی دوبارهٔ سؤال‌های تأییدشده")
    def activate_prompts(self, request, queryset):
        updated = queryset.filter(review_status=PromptReviewStatus.APPROVED).update(is_active=True)
        self.message_user(request, f"{updated} سؤال دوباره در بازی فعال شد.")

    @admin.display(description="بررسی")
    def review_controls(self, obj: Prompt):
        approve = (
            format_html(
                '<button type="submit" form="prompt-quick-review-form" '
                'name="review_action" value="APPROVED:{}" class="prompt-review-button approve">تأیید</button>',
                obj.pk,
            )
            if obj.review_status != PromptReviewStatus.APPROVED
            else ""
        )
        reject = (
            format_html(
                '<button type="submit" form="prompt-quick-review-form" '
                'name="review_action" value="REJECTED:{}" class="prompt-review-button reject">رد</button>',
                obj.pk,
            )
            if obj.review_status != PromptReviewStatus.REJECTED
            else ""
        )
        disable = (
            format_html(
                '<button type="submit" form="prompt-quick-review-form" '
                'name="review_action" value="DISABLE:{}" class="prompt-review-button disable">غیرفعال</button>',
                obj.pk,
            )
            if obj.is_active and obj.review_status == PromptReviewStatus.APPROVED
            else ""
        )
        enable = (
            format_html(
                '<button type="submit" form="prompt-quick-review-form" '
                'name="review_action" value="ENABLE:{}" class="prompt-review-button approve">فعال‌سازی</button>',
                obj.pk,
            )
            if not obj.is_active and obj.review_status == PromptReviewStatus.APPROVED
            else ""
        )
        return format_html('<span class="prompt-review-actions">{} {} {} {}</span>', approve, reject, disable, enable)

    def quick_review(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_change_permission(request):
            raise PermissionDenied

        action = request.POST.get("review_action", "")
        decision, separator, prompt_id = action.partition(":")
        if (
            separator
                and decision in (PromptReviewStatus.APPROVED, PromptReviewStatus.REJECTED, "CATEGORY", "DISABLE", "ENABLE")
            and prompt_id.isdecimal()
        ):
            category = request.POST.get(f"category_{prompt_id}")
            queryset = Prompt.objects.filter(pk=prompt_id)
            if (category is not None and category not in Category.values) or (decision == "CATEGORY" and category is None):
                self.message_user(request, "دسته‌بندی نامعتبر است؛ تغییری ذخیره نشد.", level=messages.ERROR)
                updated = None
            elif decision == "CATEGORY":
                updated = queryset.update(category=category)
            elif decision == "DISABLE":
                updated = queryset.update(is_active=False)
            elif decision == "ENABLE":
                updated = queryset.filter(review_status=PromptReviewStatus.APPROVED).update(is_active=True)
            else:
                updated = self._set_review_status(queryset, decision, request.user, category=category)
            if updated:
                verb = (
                    "تأیید شد و وارد بازی شد" if decision == PromptReviewStatus.APPROVED
                    else "دسته‌بندی‌اش ذخیره شد" if decision == "CATEGORY"
                    else "از بازی خارج شد" if decision == "DISABLE"
                    else "دوباره فعال شد" if decision == "ENABLE"
                    else "رد شد"
                )
                self.message_user(request, f"سؤال {verb}.")
            elif updated is not None:
                self.message_user(request, "سؤال پیدا نشد.", level=messages.ERROR)
        else:
            self.message_user(request, "عملیات نامعتبر است.", level=messages.ERROR)

        changelist_url = reverse("admin:game_prompt_changelist")
        return_to = request.POST.get("return_to", "")
        if return_to != changelist_url and not return_to.startswith(f"{changelist_url}?"):
            return_to = changelist_url
        return HttpResponseRedirect(return_to)

    def review_queue(self, request):
        if request.method == "POST":
            if not self.has_change_permission(request):
                raise PermissionDenied

            decision = request.POST.get("decision")
            prompt_id = request.POST.get("prompt_id")
            category = request.POST.get("prompt_category")
            if decision not in (PromptReviewStatus.APPROVED, PromptReviewStatus.REJECTED, "DISABLE", "ENABLE"):
                self.message_user(request, "عملیات نامعتبر است.", level=messages.ERROR)
            elif category is not None and category not in Category.values:
                self.message_user(request, "دسته‌بندی نامعتبر است؛ تغییری ذخیره نشد.", level=messages.ERROR)
            elif decision == "DISABLE":
                updated = Prompt.objects.filter(pk=prompt_id).update(is_active=False)
                self.message_user(request, "سؤال به‌دلیل بازخورد از بازی خارج شد." if updated else "سؤال پیدا نشد.")
            elif decision == "ENABLE":
                updated = Prompt.objects.filter(pk=prompt_id, review_status=PromptReviewStatus.APPROVED).update(is_active=True)
                self.message_user(request, "سؤال دوباره فعال شد." if updated else "فقط سؤال‌های تأییدشده قابل فعال‌سازی هستند.", level=messages.SUCCESS if updated else messages.ERROR)
            else:
                queryset = (
                    Prompt.objects.filter(pk=prompt_id)
                    if prompt_id and prompt_id.isdecimal()
                    else Prompt.objects.none()
                )
                updated = self._set_review_status(
                    queryset,
                    decision,
                    request.user,
                    request.POST.get("review_note", "").strip(),
                    category=category,
                )
                if updated:
                    verb = (
                        "تأیید شد و وارد بازی شد"
                        if decision == PromptReviewStatus.APPROVED
                        else "رد شد و از بازی خارج شد"
                    )
                    self.message_user(request, f"سؤال {verb}.")
                else:
                    self.message_user(request, "سؤال پیدا نشد.", level=messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())

        if not self.has_view_or_change_permission(request):
            raise PermissionDenied

        selected_status = request.GET.get("status", PromptReviewStatus.PENDING)
        if selected_status not in (*PromptReviewStatus.values, "ALL"):
            selected_status = PromptReviewStatus.PENDING
        selected_source = request.GET.get("source", "ALL")
        if selected_source not in (*PromptSource.values, "ALL"):
            selected_source = "ALL"
        selected_type = request.GET.get("type", "ALL")
        if selected_type not in (*PromptType.values, "ALL"):
            selected_type = "ALL"
        selected_category = request.GET.get("category", "ALL")
        if selected_category not in (*Category.values, "ALL"):
            selected_category = "ALL"
        query = request.GET.get("q", "").strip()[:100]

        prompts = self.get_queryset(request).select_related("submitted_by", "reviewed_by").order_by(
            "-created_at", "-pk"
        )
        if selected_status != "ALL":
            prompts = prompts.filter(review_status=selected_status)
        if selected_source != "ALL":
            prompts = prompts.filter(source=selected_source)
        if selected_type != "ALL":
            prompts = prompts.filter(type=selected_type)
        if selected_category != "ALL":
            prompts = prompts.filter(category=selected_category)
        if query:
            prompts = prompts.filter(
                Q(text__icontains=query)
                | Q(submitted_by__username__icontains=query)
                | Q(submitted_by__display_name__icontains=query)
            )

        counts = {
            row["review_status"]: row["total"]
            for row in Prompt.objects.values("review_status").annotate(total=Count("id"))
        }
        page = Paginator(prompts, 20).get_page(request.GET.get("page"))
        context = {
            **self.admin_site.each_context(request),
            "title": "بررسی و تأیید سؤال‌ها",
            "opts": self.model._meta,
            "page": page,
            "total_count": sum(counts.values()),
            "pending_count": counts.get(PromptReviewStatus.PENDING, 0),
            "approved_count": counts.get(PromptReviewStatus.APPROVED, 0),
            "rejected_count": counts.get(PromptReviewStatus.REJECTED, 0),
            "status": selected_status,
            "source": selected_source,
            "type": selected_type,
            "category": selected_category,
            "query": query,
            "status_choices": PromptReviewStatus.choices,
            "source_choices": PromptSource.choices,
            "type_choices": PromptType.choices,
            "category_choices": Category.choices,
            "can_change": self.has_change_permission(request),
            "changelist_url": reverse("admin:game_prompt_changelist"),
        }
        return render(request, "admin/game/prompt/review_queue.html", context)

    @admin.display(description="متن")
    def full_text(self, obj: Prompt) -> str:
        return obj.text


class TurnInline(admin.TabularInline):
    model = Turn
    extra = 0
    readonly_fields = ("index", "player", "status", "choice", "prompt", "version")


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "status", "turn_index", "started_at")
    list_filter = ("status", "category")
    raw_id_fields = ("conversation", "started_by")
    inlines = [TurnInline]
