"""Server-only provider selection, shared by generation and readiness."""
from django.conf import settings


def configuration():
    if settings.AI_PROVIDER == "anthropic":
        return {
            "provider": "anthropic", "base_url": settings.ANTHROPIC_BASE_URL,
            "token": settings.ANTHROPIC_AUTH_TOKEN, "model": settings.ANTHROPIC_MODEL,
            "headers": {"anthropic-version": settings.ANTHROPIC_API_VERSION},
        }
    if settings.AI_PROVIDER == "openai":
        return {
            "provider": "openai", "base_url": settings.OPENAI_BASE_URL,
            "token": settings.OPENAI_API_KEY, "model": settings.OPENAI_MODEL,
            "headers": settings.OPENAI_EXTRA_HEADERS,
        }
    return {"provider": settings.AI_PROVIDER, "base_url": "", "token": "", "model": "", "headers": {}}


def configured():
    config = configuration()
    return bool(config["token"] and config["model"] and config["base_url"])
