import random
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.users.models import AVATAR_CHOICES, Gender, User


class Persona(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name="ai_persona", editable=False)
    first_name = models.CharField("نام داستانی", max_length=30)
    last_name = models.CharField("نام خانوادگی داستانی", max_length=30)
    age = models.PositiveSmallIntegerField("سن", validators=[MinValueValidator(18), MaxValueValidator(100)])
    city = models.CharField("شهر داستانی", max_length=80)
    gender = models.CharField("جنسیت شخصیت", max_length=1, choices=Gender.choices, default=Gender.FEMALE)
    avatar = models.CharField("آواتار", max_length=8, choices=AVATAR_CHOICES, default="a1")
    bio = models.CharField("معرفی عمومی", max_length=160)
    interests = models.CharField("علایق عمومی", max_length=300)
    personality = models.TextField("اخلاق و شیوهٔ رفتار", max_length=3000)
    speaking_style = models.TextField("لحن و نمونهٔ دیالوگ", max_length=2000)
    backstory = models.TextField("پیشینهٔ داستانی", max_length=3000, blank=True)
    boundaries = models.TextField("مرزهای رفتاری", max_length=2000, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "شخصیت هوش مصنوعی"
        verbose_name_plural = "شخصیت‌های هوش مصنوعی"
        constraints = [models.CheckConstraint(condition=models.Q(age__gte=18, age__lte=100), name="ai_persona_adult")]

    def __str__(self):
        return f"{self.first_name} {self.last_name} · AI"

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.user_id:
            user = User(username=f"ai_{uuid.uuid4().hex[:16]}", is_ai=True, is_guest=False)
            user.set_unusable_password()
            user.save()
            self.user = user
        super().save(*args, **kwargs)
        User.objects.filter(pk=self.user_id).update(
            display_name=f"{self.first_name} {self.last_name}"[:32],
            first_name=self.first_name, last_name=self.last_name,
            gender=self.gender, avatar=self.avatar, bio=self.bio,
        )

    def public_profile(self):
        return {"first_name": self.first_name, "last_name": self.last_name,
                "age": self.age, "city": self.city, "interests": self.interests,
                "disclosure": "شخصیت داستانی هوش مصنوعی"}


def session_deadline():
    """Legacy default retained for migration 0002."""
    return timezone.now() + timedelta(minutes=10)


class AISettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    fallback_enabled = models.BooleanField("اتصال خودکار کاربران منتظر به AI", default=True)
    session_min_minutes = models.PositiveSmallIntegerField("حداقل مدت جلسه (دقیقه)", default=10,
        validators=[MinValueValidator(1), MaxValueValidator(1440)])
    session_max_minutes = models.PositiveSmallIntegerField("حداکثر مدت جلسه (دقیقه)", default=20,
        validators=[MinValueValidator(1), MaxValueValidator(1440)])

    class Meta:
        verbose_name = "تنظیمات بازی با AI"
        verbose_name_plural = "تنظیمات بازی با AI"
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="ai_settings_singleton"),
            models.CheckConstraint(condition=models.Q(session_min_minutes__gte=1,
                session_max_minutes__lte=1440, session_max_minutes__gte=models.F("session_min_minutes")),
                name="ai_settings_duration_range"),
        ]

    def __str__(self):
        return "تنظیمات بازی با AI"

    def clean(self):
        super().clean()
        if self.session_min_minutes and self.session_max_minutes and self.session_max_minutes < self.session_min_minutes:
            raise ValidationError({"session_max_minutes": "حداکثر مدت نباید کمتر از حداقل باشد."})

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def public_payload(self):
        return {"fallback_enabled": self.fallback_enabled, "session_min_minutes": self.session_min_minutes,
                "session_max_minutes": self.session_max_minutes}

def configured_session_deadline():
    config = AISettings.load()
    return timezone.now() + timedelta(seconds=random.randint(config.session_min_minutes * 60, config.session_max_minutes * 60))


class AIEncounter(models.Model):
    """Lifetime match history, independent of deletable chat history."""
    human = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT)
    first_matched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["human", "persona"], name="ai_encounter_unique_pair")]


class AIConversation(models.Model):
    """Durable work cursor. Queue delivery is a hint; Postgres owns pending work."""
    conversation = models.OneToOneField("chat.Conversation", on_delete=models.CASCADE, primary_key=True)
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT)
    human = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    started_at = models.DateTimeField("زمان شروع", default=timezone.now)
    expires_at = models.DateTimeField(default=configured_session_deadline, db_index=True)
    revision = models.PositiveBigIntegerField(default=0)
    handled_revision = models.PositiveBigIntegerField(default=0)
    lease = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    retry_at = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "گفتگوی هوش مصنوعی"
        verbose_name_plural = "گفتگوهای هوش مصنوعی"

    def __str__(self):
        return f"AI chat {self.pk}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            AIEncounter.objects.get_or_create(
                human_id=self.human_id, persona_id=self.persona_id,
                defaults={"first_matched_at": self.started_at},
            )


class DailyUsage(models.Model):
    day = models.DateField()
    # Zero is the global bucket, otherwise the human user's id.
    user_key = models.PositiveBigIntegerField(default=0)
    requests = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["day", "user_key"], name="ai_daily_usage_unique")]

    def __str__(self):
        return f"{self.day} / {self.user_key}: {self.requests}"


class AIRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE)
    revision = models.PositiveBigIntegerField()
    model = models.CharField(max_length=80)
    status = models.CharField(max_length=20, default="STARTED")
    error_code = models.CharField(max_length=64, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    deliver_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivery_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "درخواست GPT"
        verbose_name_plural = "درخواست‌ها و مصرف GPT"

    def __str__(self):
        return f"{self.pk} ({self.status})"
