from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.models import Block, Friendship, Report, ReportStatus, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "display_name",
        "gender",
        "age",
        "is_guest",
        "is_active",
        "last_seen_at",
    )
    list_filter = ("is_guest", "gender", "is_active", "is_staff")
    search_fields = ("username", "display_name")
    ordering = ("-date_joined",)
    readonly_fields = ("device_token_hash", "last_seen_at", "age")

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "پروفایل",
            {"fields": ("display_name", "avatar", "bio", "gender", "birth_date", "age")},
        ),
        (
            "حساب مهمان",
            {"fields": ("is_guest", "device_token_hash", "gender_change_count", "last_seen_at")},
        ),
    )

    @admin.display(description="سن")
    def age(self, obj: User) -> int | None:
        return obj.age


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """The moderation queue.

    Nothing here is automatic. A ban is a person deciding, because an automatic
    ban at N reports is a weapon for anyone who can organise three friends.
    """

    list_display = (
        "id",
        "created_at",
        "reason",
        "status",
        "target_user",
        "reporter",
        "has_message",
    )
    list_filter = ("status", "reason", "created_at")
    search_fields = ("note", "target_user__username", "target_user__display_name")
    raw_id_fields = ("reporter", "target_user", "target_message")
    readonly_fields = ("created_at", "reported_text")
    actions = ("mark_reviewed", "ban_target", "delete_reported_message")
    date_hierarchy = "created_at"

    @admin.display(boolean=True, description="پیام دارد")
    def has_message(self, obj: Report) -> bool:
        return obj.target_message_id is not None

    @admin.display(description="متن گزارش‌شده")
    def reported_text(self, obj: Report) -> str:
        return obj.target_message.body if obj.target_message else "—"

    @admin.action(description="علامت‌زدن به‌عنوان بررسی‌شده")
    def mark_reviewed(self, request, queryset) -> None:
        updated = queryset.update(status=ReportStatus.REVIEWED)
        self.message_user(request, f"{updated} گزارش بررسی‌شده علامت خورد.")

    @admin.action(description="مسدودکردن حساب کاربر گزارش‌شده")
    def ban_target(self, request, queryset) -> None:
        # Deactivating is enough: the WebSocket auth and the JWT layer both
        # refuse an inactive user, so existing tokens stop working too.
        user_ids = set(queryset.values_list("target_user_id", flat=True))
        User.objects.filter(pk__in=user_ids).update(is_active=False)
        queryset.update(status=ReportStatus.ACTIONED)
        self.message_user(request, f"{len(user_ids)} حساب غیرفعال شد.")

    @admin.action(description="حذف پیام گزارش‌شده")
    def delete_reported_message(self, request, queryset) -> None:
        count = 0
        for report in queryset.select_related("target_message"):
            if report.target_message and not report.target_message.is_deleted:
                report.target_message.is_deleted = True
                report.target_message.save(update_fields=["is_deleted"])
                count += 1
        queryset.update(status=ReportStatus.ACTIONED)
        self.message_user(request, f"{count} پیام حذف شد.")


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")
    raw_id_fields = ("blocker", "blocked")
    search_fields = ("blocker__username", "blocked__username")


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "status", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("from_user", "to_user", "conversation")
