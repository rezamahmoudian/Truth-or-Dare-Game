import random
import uuid
from datetime import datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.chat import services as chat
from apps.chat.models import Conversation
from apps.core.errors import DomainError
from apps.game import services as game

from . import client, services
from .models import AIConversation, AIRequest
# Register the probe on the same workers that produce replies.
from .readiness import mark_unavailable, probe_ticket  # noqa: F401


@shared_task(ignore_result=True)
def recover_pending():
    """Close timed AI rooms and redeliver lost queue notifications."""
    for conversation_id in AIConversation.objects.filter(
        expires_at__lte=timezone.now(), conversation__status="ACTIVE"
    ).values_list("pk", flat=True)[:100]:
        services.expire_session(conversation_id)
    for request_id, deliver_at in AIRequest.objects.filter(
        status="READY", deliver_at__lte=timezone.now()
    ).values_list("pk", "deliver_at")[:100]:
        services.schedule_delivery(request_id, deliver_at)
    if services.available():
        for conversation_id in services.pending_ids():
            services.dispatch(conversation_id)


def _load(conversation_id):
    return (AIConversation.objects.select_related("persona__user", "human", "conversation")
            .select_for_update(of=("self",)).filter(pk=conversation_id).first())


@shared_task(ignore_result=True)
def respond(conversation_id):
    if not services.available():
        return
    with transaction.atomic():
        state = _load(conversation_id)
        now = timezone.now()
        if not state or state.revision <= state.handled_revision:
            return
        pending = AIRequest.objects.filter(conversation=state, status="READY").first()
        if pending:
            if pending.revision == state.revision:
                transaction.on_commit(lambda: services.schedule_delivery(pending.pk, pending.deliver_at))
                return
            # A new message supersedes the unsent draft. Rebuild one reply for the
            # entire burst rather than waiting out the old draft's typing delay.
            if str(state.lease) == pending.delivery_payload.get("lease"):
                state.lease = state.lease_until = None
                state.save(update_fields=["lease", "lease_until"])
            pending.status, pending.delivery_payload, pending.finished_at = "STALE", {}, now
            pending.save(update_fields=["status", "delivery_payload", "finished_at"])
        if (state.lease_until and state.lease_until > now) or (state.retry_at and state.retry_at > now):
            return
        if not services.valid(state):
            state.handled_revision = state.revision
            state.save(update_fields=["handled_revision"])
            return
        action, signature, context = services.snapshot(state)
        if action == "wait":
            state.handled_revision = state.revision
            state.save(update_fields=["handled_revision"])
            return
        batch_ready_at = context.get("batch_ready_at")
        if batch_ready_at and datetime.fromisoformat(batch_ready_at) > now:
            transaction.on_commit(lambda: services.dispatch(
                conversation_id, eta=datetime.fromisoformat(batch_ready_at)))
            return
        try:
            with transaction.atomic():
                services.reserve_usage(state.human_id)
        except DomainError:
            state.handled_revision = state.revision
            state.last_error = "daily_limit"
            state.save(update_fields=["handled_revision", "last_error"])
            return
        token = uuid.uuid4()
        if state.retry_at is None:
            state.failures = 0
        AIRequest.objects.filter(conversation=state, status="STARTED").update(status="EXPIRED", finished_at=now)
        state.lease = token
        state.lease_until = now + timedelta(seconds=max(90, settings.AI_REQUEST_TIMEOUT * 2 + 15))
        state.save(update_fields=["lease", "lease_until", "failures"])
        revision = state.revision
        persona = state.persona
        persona_version = persona.updated_at
        request = AIRequest.objects.create(conversation=state, revision=revision, model=settings.OPENAI_MODEL)

    # No database transaction/row lock is held while waiting for GPT.
    try:
        reply, usage = client.generate(persona, context, action)
    except client.ProviderError as exc:
        mark_unavailable(exc.code)
        _failed(conversation_id, token, request.pk, revision, exc.code, exc.retryable)
        return

    try:
        with transaction.atomic():
            state = _load(conversation_id)
            if not state or state.lease != token:
                AIRequest.objects.filter(pk=request.pk).update(status="STALE", finished_at=timezone.now())
                return
            state.conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
            fresh_action, fresh_signature, fresh_context = services.snapshot(state)
            # A late network response must not answer a skipped turn, continue a
            # closed room or speak with an outdated persona definition.
            stale = (not services.valid(state) or state.revision != revision or signature != fresh_signature
                     or action != fresh_action or state.persona.updated_at != persona_version
                     or context["latest_message_id"] != fresh_context["latest_message_id"])
            deliver_at = timezone.now() + timedelta(seconds=reply_delay_seconds(reply))
            payload = {} if stale else {
                "reply": reply, "signature": list(signature) if signature else None,
                "latest_message_id": context["latest_message_id"],
                "persona_version": persona_version.isoformat(), "lease": str(token),
            }
            if stale:
                state.lease = state.lease_until = state.retry_at = None
            else:
                state.lease_until = deliver_at + timedelta(seconds=90)
            state.save(update_fields=["lease", "lease_until", "retry_at"])
            AIRequest.objects.filter(pk=request.pk).update(
                status="STALE" if stale else "READY", finished_at=timezone.now() if stale else None,
                deliver_at=None if stale else deliver_at, delivery_payload=payload,
                input_tokens=max(0, int(usage.get("input_tokens", 0))),
                output_tokens=max(0, int(usage.get("output_tokens", 0))),
            )
            if stale:
                transaction.on_commit(lambda: services.dispatch(conversation_id))
            else:
                transaction.on_commit(lambda: services.schedule_delivery(request.pk, deliver_at))
    except DomainError as exc:
        _failed(conversation_id, token, request.pk, revision, exc.code, False)


def reply_delay_seconds(reply):
    """Brief length-based pauses, capped at eight seconds after generation."""
    length = len(reply["text"].strip()) if reply["action"] != "choose" else 0
    base = min(7.0, 0.7 + length / 50)
    return round(min(8.0, base * random.uniform(0.85, 1.15)), 2)


@shared_task(ignore_result=True)
def deliver(request_id):
    request = AIRequest.objects.filter(pk=request_id, status="READY").first()
    if not request:
        return
    conversation_id = request.conversation_id
    try:
        with transaction.atomic():
            # Same lock order as generation: conversation state, then request.
            state = _load(conversation_id)
            request = AIRequest.objects.select_for_update().filter(pk=request_id, status="READY").first()
            if not request or request.deliver_at > timezone.now():
                return
            payload = request.delivery_payload
            owns_lease = bool(state and str(state.lease) == payload["lease"])
            stale = not owns_lease
            if owns_lease:
                state.conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
                action, signature, context = services.snapshot(state)
                signature = list(signature) if signature else None
                stale = (not services.valid(state) or state.revision != request.revision
                         or signature != payload["signature"] or action != payload["reply"]["action"]
                         or context["latest_message_id"] != payload["latest_message_id"]
                         or state.persona.updated_at.isoformat() != payload["persona_version"])
                if not stale:
                    _apply(state, payload["reply"], signature, request.pk)
                    state.handled_revision = request.revision
                    state.failures = 0
                    state.last_error = ""
                state.lease = state.lease_until = state.retry_at = None
                state.save(update_fields=["handled_revision", "failures", "last_error", "lease", "lease_until", "retry_at"])
                if stale:
                    transaction.on_commit(lambda: services.dispatch(conversation_id))
            request.status = "STALE" if stale else "DONE"
            request.finished_at = timezone.now()
            request.delivery_payload = {}
            request.save(update_fields=["status", "finished_at", "delivery_payload"])
    except DomainError as exc:
        _failed(conversation_id, uuid.UUID(payload["lease"]), request_id,
                request.revision, exc.code, False)


def _apply(state, reply, signature, request_id):
    actor = state.persona.user
    action = reply["action"]
    if action == "choose":
        # Enforce the product rule even if a provider returns an unexpected choice.
        try:
            game.choose(actor, signature[0], "TRUTH")
        except DomainError as exc:
            if exc.code != "prompts_exhausted":
                raise
            chat.post_system_message(
                state.conversation,
                "سؤال حقیقت تازه‌ای برای این بازی باقی نمانده؛ نوبت شخصیت AI رد شد.",
                meta={"game": "prompts_exhausted"},
            )
            game.skip(actor, signature[0])
    elif action == "answer":
        game.answer(actor, signature[0], reply["text"])
    else:
        chat.post_message(conversation=state.conversation, sender=actor, body=reply["text"],
                          client_id=f"ai-{request_id.hex}", meta={"ai_generated": True})
        if action == "confirm":
            game.confirm(actor, signature[0])


def _failed(conversation_id, token, request_id, revision, code, retryable):
    with transaction.atomic():
        AIRequest.objects.filter(pk=request_id).update(status="FAILED", error_code=code,
                                                      finished_at=timezone.now(), delivery_payload={})
        state = _load(conversation_id)
        if not state or state.lease != token:
            return
        state.failures += 1
        state.lease = state.lease_until = None
        if retryable and state.failures < 3:
            state.retry_at = timezone.now() + timedelta(seconds=5 * state.failures)
        else:
            state.handled_revision = revision
            state.retry_at = None
            # Keep diagnostics in the database without posting a chat message.
        state.last_error = code
        state.save()
