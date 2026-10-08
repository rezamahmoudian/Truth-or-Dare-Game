from django.urls import path, re_path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users import invitation_views, views
from apps.users.photos import ProfilePhotoView, ProfilePhotoFileView

app_name = "users"

urlpatterns = [
    path("users/me/photo/", ProfilePhotoView.as_view(), name="profile-photo"),
    re_path(r"^profile-photos/(?P<filename>[a-f0-9]{32}\.jpg)/$", ProfilePhotoFileView.as_view()),
    path("game-invitations/", invitation_views.InvitationListView.as_view()),
    path("people/<int:user_id>/invite/", invitation_views.InvitationSendView.as_view()),
    path("game-invitations/<int:invitation_id>/<str:action>/", invitation_views.InvitationRespondView.as_view()),
    path("auth/guest/", views.GuestAuthView.as_view(), name="auth-guest"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/upgrade/", views.UpgradeAccountView.as_view(), name="auth-upgrade"),
    path("users/me/", views.MeView.as_view(), name="me"),
    path("friends/", views.FriendListView.as_view(), name="friends"),
    path("friends/<int:user_id>/", views.FriendRequestView.as_view(), name="friend"),
    path(
        "friends/<int:user_id>/accept/",
        views.FriendAcceptView.as_view(),
        name="friend-accept",
    ),
    path(
        "friends/<int:user_id>/decline/",
        views.FriendDeclineView.as_view(),
        name="friend-decline",
    ),
    path("people/<int:user_id>/", views.PublicProfileView.as_view(), name="person"),
    path("users/<str:username>/", views.PublicProfileView.as_view(), name="profile"),
]
