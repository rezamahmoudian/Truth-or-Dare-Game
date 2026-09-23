import logging

from celery import shared_task

logger = logging.getLogger("ft.match")


@shared_task(ignore_result=True)
def run_matcher() -> dict:
    """One matcher pass, scheduled by beat.

    Runs on a short tick rather than reacting to each enqueue: a tick is
    self-healing (a missed one is covered by the next) and it gives the matcher
    a whole pool to work with instead of deciding on one arrival at a time,
    which is what makes group modes and priority ordering possible at all.
    """
    from apps.matchmaking import services

    try:
        summary = services.run_matcher()
    except Exception:
        logger.exception("mm.matcher_failed")
        return {"error": True}

    if summary.get("matched") or summary.get("expired"):
        logger.info("mm.matcher_pass", extra={"event": "mm.matcher_pass", **summary})
    return summary
