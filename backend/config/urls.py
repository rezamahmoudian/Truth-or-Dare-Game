from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.chat.urls")),
    path("api/", include("apps.game.urls")),
    path("api/", include("apps.matchmaking.urls")),
    path("api/", include("apps.moderation.urls")),
    path("api/", include("apps.ai_players.urls")),
]

if settings.DEBUG:
    # Uvicorn does not provide runserver's automatic static-file wrapper.
    # The admin CSS/JS must have explicit development routes.
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
