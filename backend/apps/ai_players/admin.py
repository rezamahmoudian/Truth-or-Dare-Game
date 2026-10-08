from django.contrib import admin
from django.utils.html import format_html

from .models import AIConversation, AIRequest, AISettings, Persona


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "fallback_enabled", "session_min_minutes", "session_max_minutes")
    fields = ("fallback_enabled", "session_min_minutes", "session_max_minutes")

    def has_add_permission(self, request):
        return not AISettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["fallback_enabled"].help_text = "برای همهٔ کاربران واجد شرایطِ بازی دونفره پس از ۲ دقیقه انتظار. خاموش‌کردن، اتصال‌های بعدی را متوقف می‌کند و جلسه‌های جاری ادامه دارند. سرویس GPT باید در سرور فعال باشد."
        form.base_fields["session_max_minutes"].help_text = "مدت تصادفی هر جلسهٔ جدید بین حداقل و حداکثر انتخاب می‌شود. تغییرات فوراً برای جلسه‌های جدید اعمال می‌شود؛ زمان جلسه‌های جاری ثابت می‌ماند."
        return form


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("profile_photo_preview", "first_name", "last_name", "age", "city", "gender", "is_active")
    list_display_links = ("first_name",)
    list_select_related = ("user",)
    list_filter = ("is_active", "gender", "city")
    search_fields = ("first_name", "last_name", "city", "interests")
    readonly_fields = ("user", "updated_at", "profile_photo_preview")
    fieldsets = (
        ("پروفایل عمومی شخصیت داستانی", {"fields": ("profile_photo_preview", "first_name", "last_name", "age", "city", "gender", "avatar", "bio", "interests")}),
        ("شخصیت و رفتار (فقط برای مدیر و مدل)", {"fields": ("personality", "speaking_style", "backstory", "boundaries")}),
        ("فعال‌سازی", {"fields": ("is_active", "user", "updated_at"),
                     "description": "همهٔ شخصیت‌ها در بازی با نشان هوش مصنوعی معرفی می‌شوند. کلید API فقط در تنظیمات سرور نگهداری می‌شود."}),
    )

    @admin.display(description="عکس پروفایل")
    def profile_photo_preview(self, obj):
        if not obj or not obj.user_id or not obj.user.avatar_url:
            return "بدون عکس"
        return format_html(
            '<img src="{}" alt="{}" width="64" height="64" style="border-radius:50%;object-fit:cover" />',
            obj.user.avatar_url, obj.first_name,
        )

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AIRequest)
class AIRequestAdmin(ReadOnlyAdmin):
    list_display = ("id", "conversation", "model", "status", "input_tokens", "output_tokens", "error_code", "created_at")
    list_filter = ("status", "model", "created_at")


@admin.register(AIConversation)
class AIConversationAdmin(ReadOnlyAdmin):
    list_display = ("conversation", "persona", "human", "started_at", "expires_at", "revision", "handled_revision", "last_error")
    list_filter = ("persona", "last_error")
