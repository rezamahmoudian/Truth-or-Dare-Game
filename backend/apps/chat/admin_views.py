from urllib.parse import urlencode

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Prefetch
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.chat.attachments import private_storage
from apps.chat import services
from apps.chat.models import Conversation, Message, Participant


def _require_permission(request, codename="view_chat_transcript"):
    if not request.user.is_active or not request.user.is_staff:
        raise PermissionDenied
    if not request.user.is_superuser and not request.user.has_perm(f"chat.{codename}"):
        raise PermissionDenied


def _participant_queryset():
    return Participant.objects.select_related("user").order_by("joined_at")


def review_index(request):
    """Search conversations by participant and open them in the reviewer UI."""
    _require_permission(request)
    query = request.GET.get("q", "").strip()[:100]

    conversations = Conversation.objects.all()
    if query:
        conversations = conversations.filter(
            Q(participants__user__username__icontains=query)
            | Q(participants__user__display_name__icontains=query)
            | Q(participants__user__ai_persona__first_name__icontains=query)
            | Q(participants__user__ai_persona__last_name__icontains=query)
        ).distinct()
    conversations = (
        conversations.annotate(message_count=Count("messages", distinct=True))
        .prefetch_related(Prefetch("participants", queryset=_participant_queryset()))
        .order_by("-last_message_at", "-created_at")
    )

    page = Paginator(conversations, 20).get_page(request.GET.get("page"))
    # A search result is easier to identify when it shows both ends of the
    # conversation.  Keep the list query cheap by fetching the first visible
    # message for the current page in one additional query.
    page_conversation_ids = [conversation.pk for conversation in page.object_list]
    first_message_by_conversation = {}
    if page_conversation_ids:
        first_messages = (
            Message.objects.filter(conversation_id__in=page_conversation_ids, is_deleted=False)
            .exclude(type="SYSTEM")
            .order_by("conversation_id", "id")
        )
        for message in first_messages:
            first_message_by_conversation.setdefault(message.conversation_id, message.body)
    for conversation in page.object_list:
        conversation.first_message_preview = first_message_by_conversation.get(conversation.pk, "")
    return render(
        request,
        "admin/chat/review_index.html",
        {
            **admin.site.each_context(request),
            "title": "بررسی گفتگوها",
            "query": query,
            "page": page,
            "review_url": reverse("chat_admin_reviews"),
        },
    )


def review_detail(request, conversation_id):
    """Read-only transcript view; messages are paginated from newest backwards."""
    _require_permission(request)
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related(
            Prefetch("participants", queryset=_participant_queryset())
        ),
        pk=conversation_id,
    )
    messages = conversation.messages.select_related("sender").order_by("id")
    paginator = Paginator(messages, 100)
    page = paginator.get_page(request.GET.get("page") or paginator.num_pages or 1)
    participants = list(conversation.participants.all())
    first_participant_id = participants[0].user_id if participants else None
    human_participants = [participant for participant in participants if not participant.user.is_ai]
    query = request.GET.get("q", "").strip()[:100]
    return render(
        request,
        "admin/chat/review_detail.html",
        {
            **admin.site.each_context(request),
            "title": "گفتگوی ثبت‌شده",
            "conversation": conversation,
            "participants": participants,
            "first_participant_id": first_participant_id,
            "human_participants": human_participants,
            "page": page,
            "query": query,
            "review_url": reverse("chat_admin_reviews"),
            "can_view_media": request.user.is_superuser
            or request.user.has_perm("chat.view_chat_transcript_media"),
        },
    )


def send_system_message(request, conversation_id):
    """Send a staff-authored notice to a participant's system inbox."""
    _require_permission(request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    conversation = get_object_or_404(Conversation, pk=conversation_id)
    target_id = str(request.POST.get("target_user_id") or "").strip()
    body = str(request.POST.get("body") or "").strip()
    target = None
    if target_id.isdecimal():
        target = (
            Participant.objects.select_related("user")
            .filter(conversation=conversation, user_id=int(target_id), user__is_ai=False)
            .first()
        )
    if target is None:
        messages.error(request, "کاربر مقصد این گفتگو پیدا نشد.")
    elif not body:
        messages.error(request, "متن پیام سیستم را وارد کنید.")
    elif len(body) > 2000:
        messages.error(request, "متن پیام نباید بیشتر از ۲۰۰۰ نویسه باشد.")
    else:
        system_conversation = services.get_or_create_system_conversation(target.user)
        services.post_system_message(
            system_conversation,
            body,
            meta={
                "system_kind": "admin_notice",
                "sent_by_admin_id": request.user.pk,
            },
        )
        messages.success(request, "پیام سیستم برای کاربر ارسال شد.")

    query = request.POST.get("q", "").strip()[:100]
    url = reverse("chat_admin_review_detail", args=[conversation.pk])
    return redirect(f"{url}?{urlencode({'q': query})}" if query else url)


def review_attachment(request, conversation_id, message_id):
    _require_permission(request)
    if not request.user.is_superuser and not request.user.has_perm(
        "chat.view_chat_transcript_media"
    ):
        raise PermissionDenied
    message = get_object_or_404(
        Message.objects.filter(
            pk=message_id, conversation_id=conversation_id, is_deleted=False
        )
    )
    if not message.attachment:
        raise PermissionDenied
    try:
        file = private_storage().open(message.attachment.name, "rb")
    except FileNotFoundError:
        raise Http404("attachment not found")
    response = FileResponse(
        file,
        as_attachment=False,
        filename=message.attachment_info.get("name", "file"),
        content_type=message.attachment_info.get("mime", "application/octet-stream"),
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response
