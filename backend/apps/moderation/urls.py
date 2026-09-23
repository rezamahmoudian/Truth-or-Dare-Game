from django.urls import path

from apps.moderation import views

app_name = "moderation"

urlpatterns = [
    path("reports/reasons/", views.ReasonListView.as_view(), name="reasons"),
    path("reports/", views.ReportView.as_view(), name="report"),
    path("blocks/", views.BlockListView.as_view(), name="blocks"),
    path("blocks/<int:user_id>/", views.BlockView.as_view(), name="block"),
    path(
        "messages/<int:message_id>/",
        views.MessageDeleteView.as_view(),
        name="message-delete",
    ),
]
