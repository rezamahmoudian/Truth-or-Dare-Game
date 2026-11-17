from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from apps.chat import admin_views as chat_admin_views

urlpatterns = [
    path(
        "admin/chat/reviews/",
        admin.site.admin_view(chat_admin_views.review_index),
        name="chat_admin_reviews",
    ),
    path(
        "admin/chat/reviews/<uuid:conversation_id>/",
        admin.site.admin_view(chat_admin_views.review_detail),
        name="chat_admin_review_detail",
    ),
    path(
        "admin/chat/reviews/<uuid:conversation_id>/send-system/",
        admin.site.admin_view(chat_admin_views.send_system_message),
        name="chat_admin_send_system",
    ),
    path(
        "admin/chat/reviews/<uuid:conversation_id>/attachments/<int:message_id>/",
        admin.site.admin_view(chat_admin_views.review_attachment),
        name="chat_admin_review_attachment",
    ),
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.chat.urls")),
    path("api/", include("apps.game.urls")),
    path("api/", include("apps.matchmaking.urls")),
    path("api/", include("apps.moderation.urls")),
    path("api/", include("apps.ai_players.urls")),
    path("api/billing/", include("apps.billing.urls")),
]

if settings.DEBUG:
    # Uvicorn does not provide runserver's automatic static-file wrapper.
    # The admin CSS/JS must have explicit development routes.
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
