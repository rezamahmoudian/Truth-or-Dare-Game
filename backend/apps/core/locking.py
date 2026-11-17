"""Postgres transaction locks for per-player queue/pair coordination.

Separate from User row locks: game statistics update User while holding a
conversation lock. Using that row as the queue mutex would invert lock order.
All pair creators and queue state writers must use this guard before rooms.
"""
from django.db import connection


def lock_players(user_ids):
    if not connection.in_atomic_block:
        raise RuntimeError("Player locks require an atomic transaction")
    with connection.cursor() as cursor:
        for user_id in sorted(set(user_ids)):
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"ft:player:{user_id}"])
