from django.conf import settings
from rest_framework.permissions import BasePermission


class MonetizationEnabled(BasePermission):
    message = "امکانات فروشگاه فعلاً غیرفعال است."

    def has_permission(self, request, view):
        return settings.MONETIZATION_ENABLED
