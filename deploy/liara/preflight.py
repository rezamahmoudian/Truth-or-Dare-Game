"""Validate deployment configuration without printing secrets."""
import os
import sys
import time
from urllib.parse import urlsplit


def validate(env):
    errors = []
    for name in ("DJANGO_SECRET_KEY", "DATABASE_URL", "REDIS_URL", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS"):
        if not env.get(name, "").strip():
            errors.append(f"Set {name} in Liara environment variables.")
    key = env.get("DJANGO_SECRET_KEY", "")
    if len(key) < 32 or key.lower().startswith(("change-", "dev-", "your-")):
        errors.append("DJANGO_SECRET_KEY must be a new random secret of at least 32 characters.")
    if env.get("DEBUG", "False").lower() not in ("false", "0", "no", "off"):
        errors.append("DEBUG must be False on Liara.")
    if "*" in env.get("ALLOWED_HOSTS", ""):
        errors.append("ALLOWED_HOSTS must contain your actual domain, not a wildcard.")
    for name, schemes in (("DATABASE_URL", ("postgres", "postgresql")), ("REDIS_URL", ("redis", "rediss"))):
        try:
            url = urlsplit(env.get(name, ""))
            if url.scheme not in schemes or not url.hostname:
                errors.append(f"{name} must be a valid service connection URL.")
        except ValueError:
            errors.append(f"{name} is invalid.")
    for name in ("UVICORN_WORKERS", "CELERY_CONCURRENCY"):
        if not env.get(name, "2").isdigit() or not 1 <= int(env.get(name, "2")) <= 32:
            errors.append(f"{name} must be between 1 and 32.")
    return errors


def main():
    errors = validate(os.environ)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    import psycopg
    import redis

    deadline = time.monotonic() + 60
    while True:
        try:
            with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as conn:
                conn.execute("SELECT 1")
            with redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=5, socket_timeout=5) as cache:
                cache.ping()
            print("PostgreSQL and Redis are reachable.", flush=True)
            return 0
        except (psycopg.Error, redis.RedisError):
            if time.monotonic() >= deadline:
                print("PostgreSQL or Redis is unavailable; check URLs, credentials and network placement in Liara.", file=sys.stderr)
                return 1
            print("Waiting for PostgreSQL and Redis...", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
