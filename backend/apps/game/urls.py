from django.urls import path

from apps.game import views

app_name = "game"

urlpatterns = [
    path("game/categories/", views.CategoryListView.as_view(), name="categories"),
    path(
        "conversations/<uuid:conversation_id>/game/",
        views.GameStateView.as_view(),
        name="state",
    ),
]
