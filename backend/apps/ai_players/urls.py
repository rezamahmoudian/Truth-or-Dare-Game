from django.urls import path

from .views import PersonaListView, RetryView

urlpatterns = [
    path("ai/personas/", PersonaListView.as_view()),
    path("conversations/<uuid:conversation_id>/ai/retry/", RetryView.as_view()),
]
