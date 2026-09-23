"""
Django settings for the Truth-or-Dare social game.

Single env-driven settings module: every difference between development and
production is an environment variable, so there is one code path to reason
about and nothing that only breaks in prod.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["*"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    SENTRY_DSN=(str, ""),
)
environ.Env.read_env(REPO_ROOT / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-secret-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "channels",
]

LOCAL_APPS = [
    "apps.core",
    "apps.users",
    "apps.chat",
    "apps.game",
    "apps.matchmaking",
    "apps.moderation",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------------
# Data stores
# --------------------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://ft:ft@localhost:5432/ft",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Channels fans WebSocket events out through Redis. Note this is pub/sub only —
# durable state belongs in Postgres, per the project architecture rules.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("CHANNEL_REDIS_URL", default=REDIS_URL)]},
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = env("TIME_ZONE", default="Asia/Tehran")

# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

# Declared before the first migration on purpose: swapping AUTH_USER_MODEL
# after tables exist is one of the most painful migrations in Django.
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    # Behind Caddy every request arrives from the proxy's IP, so without this
    # the whole internet shares one throttle bucket and the rate limit protects
    # nothing. Set to the number of proxies in front of Django in production;
    # left unset in dev, where requests really do come from the client.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=None),
    "DEFAULT_THROTTLE_RATES": {
        # The guest endpoint mints accounts for anyone who asks, so it is the
        # obvious target for someone scripting a few thousand of them.
        "auth": env("THROTTLE_AUTH", default="20/hour"),
        "profile": env("THROTTLE_PROFILE", default="60/hour"),
        # Joining and leaving the queue repeatedly is cheap for the user and
        # expensive for the matcher.
        "match": env("THROTTLE_MATCH", default="120/hour"),
    },
}

SIMPLE_JWT = {
    # Long-lived on purpose. A guest has no password to recover with, so being
    # logged out is not an inconvenience — it is losing the account, along with
    # every friend and conversation attached to it.
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=env.int("JWT_ACCESS_HOURS", default=6)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=180)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --------------------------------------------------------------------------
# Product rules that belong in configuration rather than scattered in code
# --------------------------------------------------------------------------

# Strangers, private chat and "dare" content. The gate is enforced server-side
# against a stored birth date, not a checkbox.
MIN_AGE = env.int("MIN_AGE", default=18)

# Gender decides which match queues a user can enter, so it cannot be a field
# people flip at will. One correction after the initial choice.
MAX_GENDER_CHANGES = env.int("MAX_GENDER_CHANGES", default=1)

# How many turns each player gets before the game ends. There are deliberately
# no turn timings: a turn waits for a person, never for a clock.
GAME_DEFAULT_ROUNDS = env.int("GAME_DEFAULT_ROUNDS", default=3)

# Matchmaking. A ticket that has waited this long is expired with a concrete
# suggestion rather than left spinning — an unbounded wait is how these
# products lose someone on their first visit.
MATCH_TICKET_TTL_SECONDS = env.int("MATCH_TICKET_TTL_SECONDS", default=180)
# Being handed the same stranger twice in a row makes the pool feel empty.
MATCH_RECENT_PARTNER_MINUTES = env.int("MATCH_RECENT_PARTNER_MINUTES", default=30)

# How recently someone must have been seen to count as "around" on the lobby.
LOBBY_ACTIVE_MINUTES = env.int("LOBBY_ACTIVE_MINUTES", default=10)

# --------------------------------------------------------------------------
# Localisation — the product is Persian and RTL
# --------------------------------------------------------------------------

LANGUAGE_CODE = "fa-ir"
TIME_ZONE = env("TIME_ZONE", default="Asia/Tehran")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static files
# --------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Message ids must be bigints so unread counts and cursor pagination reduce to
# integer comparison. See the project architecture rules.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# CORS — normally unused: the Vite dev server and Caddy both proxy /api and
# /ws same-origin. Kept for the case where the frontend is served elsewhere.
# --------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# --------------------------------------------------------------------------
# Security (no-ops while DEBUG is on)
# --------------------------------------------------------------------------

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# --------------------------------------------------------------------------
# Logging — JSON from day one so production logs are greppable and the event
# counters the roadmap calls for are machine-readable.
# --------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "config.logging.JsonFormatter"},
        "console": {"format": "{levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "console" if DEBUG else "json",
        },
    },
    "root": {"handlers": ["stdout"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "propagate": True},
        "ft": {"level": env("LOG_LEVEL", default="INFO"), "propagate": True},
    },
}

# --------------------------------------------------------------------------
# Sentry — only wired up when a DSN is present, so local dev stays silent.
# --------------------------------------------------------------------------

SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", default="development"),
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
        send_default_pii=False,
    )
