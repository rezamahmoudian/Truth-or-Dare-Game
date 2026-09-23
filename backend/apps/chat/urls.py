from django.urls import path

from apps.chat import views

app_name = "chat"

urlpatterns = [
    path("conversations/", views.ConversationListView.as_view(), name="list"),
    path("conversations/rooms/", views.RoomCreateView.as_view(), name="room-create"),
    path("conversations/join/", views.RoomJoinView.as_view(), name="room-join"),
    path(
        "conversations/<uuid:conversation_id>/",
        views.ConversationDetailView.as_view(),
        name="detail",
    ),
    path(
        "conversations/<uuid:conversation_id>/delete/",
        views.DeleteConversationView.as_view(),
        name="delete",
    ),
    path(
        "conversations/<uuid:conversation_id>/messages/",
        views.MessageListView.as_view(),
        name="messages",
    ),
    path(
        "conversations/<uuid:conversation_id>/read/",
        views.MarkReadView.as_view(),
        name="read",
    ),
    path(
        "conversations/<uuid:conversation_id>/close/",
        views.CloseRoomView.as_view(),
        name="close",
    ),
    path(
        "conversations/<uuid:conversation_id>/leave/",
        views.LeaveView.as_view(),
        name="leave",
    ),
]
