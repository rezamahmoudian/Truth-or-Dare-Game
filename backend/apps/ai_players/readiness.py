"""Fail-closed, per-ticket provider checks, performed by the reply workers."""
import hashlib
import json
import logging
import uuid

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from kombu.exceptions import OperationalError

from apps.core.errors import DomainError

from . import client
from .models import Persona

logger = logging.getLogger("ft.ai")
READY_SECONDS = 15
FAILURE_SECONDS = 30


def provider_key():
    # Changing provider, credential, model or headers invalidates old results.
    config = [settings.OPENAI_BASE_URL, settings.OPENAI_API_KEY,
              settings.OPENAI_MODEL, settings.OPENAI_EXTRA_HEADERS]
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    return f"ai:readiness:{digest}"


def ticket_key(ticket_id):
    return f"{provider_key()}:ticket:{ticket_id}"


def mark_unavailable(code):
    # Only codes, never provider bodies, credentials or conversation content.
    cache.set(f"{provider_key()}:down", code, timeout=FAILURE_SECONDS)
    logger.warning("ai.provider_unavailable: %s", code, extra={"error_code": code})


def ready_for_ticket(ticket):
    from .services import available
    if not available() or cache.get(f"{provider_key()}:down"):
        return False
    key = ticket_key(ticket.pk)
    result = cache.get(key)
    if result == "ready":
        return True
    if result:
        return False
    token = uuid.uuid4().hex
    if cache.add(key, token, timeout=max(60, settings.AI_REQUEST_TIMEOUT + 30)):
        transaction.on_commit(lambda: _schedule(ticket.pk, key, token))
    return False


def _schedule(ticket_id, key, token):
    try:
        probe_ticket.delay(ticket_id, key, token)
    except (OperationalError, OSError):
        if cache.get(key) == token:
            cache.delete(key)
        logger.warning("ai.readiness_queue_unavailable")


@shared_task(ignore_result=True)
def probe_ticket(ticket_id, key, token):
    from apps.matchmaking.models import MatchTicket, TicketState
    from .services import assert_available, reserve_usage

    if key != ticket_key(ticket_id) or cache.get(key) != token:
        return
    if not cache.add(f"{key}:running:{token}", True, timeout=max(60, settings.AI_REQUEST_TIMEOUT + 30)):
        return
    ticket = MatchTicket.objects.select_related("user").filter(pk=ticket_id, state=TicketState.QUEUED).first()
    if not ticket:
        cache.delete(key)
        return
    try:
        assert_available(ticket.user)
        with transaction.atomic():
            reserve_usage(ticket.user_id)
        # Exercise the same endpoint/model/schema as chat, without sending user data.
        persona = Persona(first_name="Test", last_name="Player", age=25, city="Fictional",
                          bio="Test character", interests="games", personality="friendly",
                          speaking_style="brief")
        client.generate(persona, {"history": [], "pending_user_messages": [
            {"text": "Say hello briefly.", "attachment": None}], "turn": None}, "chat")
    except client.ProviderError as exc:
        mark_unavailable(exc.code)
        if cache.get(key) == token:
            cache.set(key, "failed", timeout=FAILURE_SECONDS)
        return
    except DomainError as exc:
        if cache.get(key) == token:
            cache.set(key, "failed", timeout=FAILURE_SECONDS)
        logger.warning("ai.readiness_ineligible: %s", exc.code, extra={"error_code": exc.code})
        return
    if key == ticket_key(ticket_id) and cache.get(key) == token:
        cache.set(key, "ready", timeout=READY_SECONDS)
