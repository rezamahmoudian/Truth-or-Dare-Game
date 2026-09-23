"""Redis lock that serialises the matcher.

Matching must happen in one place at a time. If two workers each decide a pair
is compatible, both create a room and the two people end up in different rooms
waiting for someone who is elsewhere — a bug that is very hard to reproduce
from the outside and very cheap to prevent here.
"""

import contextlib
import secrets

import redis
from django.conf import settings

_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)

# Releasing only our own token: a run that overshoots the TTL must not release
# a lock a later run has since taken.
_RELEASE = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


@contextlib.contextmanager
def redis_lock(key: str, ttl_seconds: int = 15):
    """Yield True if the lock was acquired, False if someone else holds it.

    The TTL is the safety net: a worker that dies mid-run releases the lock by
    expiry rather than blocking matchmaking until someone notices.
    """
    client = redis.Redis(connection_pool=_pool)
    token = secrets.token_hex(16)
    acquired = bool(client.set(key, token, nx=True, ex=ttl_seconds))
    try:
        yield acquired
    finally:
        if acquired:
            client.eval(_RELEASE, 1, key, token)
