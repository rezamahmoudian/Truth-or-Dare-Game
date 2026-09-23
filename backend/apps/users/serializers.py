import re
from datetime import date

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.core.utils import fa_digits
from apps.users.models import User

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")


def validate_handle(value: str) -> str:
    value = value.strip().lower()
    if not USERNAME_RE.match(value):
        raise serializers.ValidationError(
            "نام کاربری باید بین ۳ تا ۲۰ کاراکتر و فقط شامل حروف انگلیسی، عدد و _ باشد."
        )
    return value


class GuestAuthSerializer(serializers.Serializer):
    """Sign in (or silently sign up) with a client-generated device token."""

    # 32 chars is the floor for a value that has to survive being a bearer
    # credential; the client generates 256 bits of randomness.
    device_token = serializers.CharField(min_length=32, max_length=128, write_only=True)


class PublicUserSerializer(serializers.ModelSerializer):
    """What other players may see.

    Note what is absent: birth_date. The exact date is unnecessary for anyone
    else and is a real identifier, so only the derived age leaves the server.
    """

    age = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "display_name", "avatar", "bio", "gender", "age")
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(read_only=True)
    is_onboarded = serializers.BooleanField(read_only=True)
    can_change_gender = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "display_name",
            "avatar",
            "bio",
            "gender",
            "birth_date",
            "age",
            "is_guest",
            "is_onboarded",
            "can_change_gender",
            "streak_days",
        )
        read_only_fields = ("id", "is_guest", "streak_days")

    # --- field-level rules ------------------------------------------------

    def validate_username(self, value: str) -> str:
        value = validate_handle(value)
        taken = User.objects.filter(username__iexact=value)
        if self.instance:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("این نام کاربری قبلاً گرفته شده است.")
        return value

    def validate_display_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("نام نمایشی خیلی کوتاه است.")
        return value

    def validate_birth_date(self, value: date) -> date:
        today = date.today()
        if value > today:
            raise serializers.ValidationError("تاریخ تولد نمی‌تواند در آینده باشد.")
        if value.year < today.year - 100:
            raise serializers.ValidationError("تاریخ تولد معتبر نیست.")

        age = today.year - value.year - (
            0 if (today.month, today.day) >= (value.month, value.day) else 1
        )
        if age < settings.MIN_AGE:
            raise serializers.ValidationError(
                f"برای استفاده از این برنامه باید حداقل {fa_digits(settings.MIN_AGE)} "
                "سال داشته باشید."
            )

        # Write-once. An age gate that lets you edit the date afterwards is not
        # a gate — anyone refused at signup would simply change the number.
        if self.instance and self.instance.birth_date:
            raise serializers.ValidationError("تاریخ تولد قابل تغییر نیست.")

        return value

    def validate_gender(self, value: str) -> str:
        changing = (
            self.instance and self.instance.gender and self.instance.gender != value
        )
        if changing and not self.instance.can_change_gender:
            raise serializers.ValidationError(
                "جنسیت قابل تغییر نیست. برای اصلاح با پشتیبانی تماس بگیرید."
            )
        return value

    def update(self, instance: User, validated_data: dict) -> User:
        new_gender = validated_data.get("gender")
        if new_gender and instance.gender and new_gender != instance.gender:
            instance.gender_change_count += 1
            if "gender_change_count" not in validated_data:
                validated_data["gender_change_count"] = instance.gender_change_count
        return super().update(instance, validated_data)


class UpgradeAccountSerializer(serializers.Serializer):
    """Turn a guest into a permanent account.

    The point is recovery across devices: a guest who clears their browser has
    lost every friendship and conversation they built, and that loss is
    invisible until it happens.
    """

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate_username(self, value: str) -> str:
        value = validate_handle(value)
        user = self.context["request"].user
        if User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("این نام کاربری قبلاً گرفته شده است.")
        return value

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value
