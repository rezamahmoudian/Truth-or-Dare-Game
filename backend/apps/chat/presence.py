"""Who is currently looking at a conversation.

Kept in Redis rather than Postgres because it is worthless a minute after it is
written and would otherwise be a database write on every heartbeat. A sorted
set scored by timestamp gives per-member expiry, which plain Redis sets cannot:
a client that vanishes without closing its socket stops refreshing its score
and ages out on its own.
"""

import time

import redis
from django.conf import settings

# How long a heartbeat counts for. Comfortably longer than the client's ping
# interval so one dropped packet does not make someone flicker offline.
TTL_SECONDS = 45
APP_ONLINE_KEY = "app:online"

_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)


def _client() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)


def _key(conversation_id) -> str:
    return f"conv:{conversation_id}:online"


def mark_online(conversation_id, user_id: int) -> None:
    key = _key(conversation_id)
    pipe = _client().pipeline()
    pipe.zadd(key, {str(user_id): time.time()})
    # The key itself expires too, so rooms nobody returns to do not accumulate.
    pipe.expire(key, TTL_SECONDS * 4)
    pipe.execute()


def mark_offline(conversation_id, user_id: int) -> None:
    _client().zrem(_key(conversation_id), str(user_id))


def online_user_ids(conversation_id) -> list[int]:
    key = _key(conversation_id)
    pipe = _client().pipeline()
    pipe.zremrangebyscore(key, "-inf", time.time() - TTL_SECONDS)
    pipe.zrange(key, 0, -1)
    _, members = pipe.execute()
    return [int(member) for member in members]


def mark_app_online(user_id: int, connection: str) -> None:
    pipe = _client().pipeline()
    pipe.zadd(APP_ONLINE_KEY, {f"{user_id}:{connection}": time.time()})
    pipe.expire(APP_ONLINE_KEY, TTL_SECONDS * 4)
    pipe.execute()


def mark_app_offline(user_id: int, connection: str) -> None:
    _client().zrem(APP_ONLINE_KEY, f"{user_id}:{connection}")


def app_online_ids() -> list[int]:
    pipe = _client().pipeline()
    pipe.zremrangebyscore(APP_ONLINE_KEY, "-inf", time.time() - TTL_SECONDS)
    pipe.zrange(APP_ONLINE_KEY, 0, -1)
    _, members = pipe.execute()
    return list({int(member.split(":", 1)[0]) for member in members})
