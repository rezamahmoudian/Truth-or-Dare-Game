from django.urls import path

from apps.matchmaking import views

app_name = "matchmaking"

urlpatterns = [
    path("lobby/", views.LobbyView.as_view(), name="lobby"),
    path("match-modes/", views.ModeListView.as_view(), name="modes"),
    path("match/", views.MatchView.as_view(), name="match"),
]
