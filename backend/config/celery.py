import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("ft")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# A short tick rather than a job per enqueue: the matcher works on the whole
# pool at once, which is what lets it fill group rooms and give the scarce side
# of a gender queue priority. Two seconds is invisible to someone watching a
# waiting screen and a twentieth of the work of a one-second tick.
app.conf.beat_schedule = {
    "matchmaking-tick": {
        "task": "apps.matchmaking.tasks.run_matcher",
        "schedule": 2.0,
    },
}


@app.task(bind=True)
def debug_task(self) -> str:
    """Smoke test for the worker; safe to delete once real tasks exist.

    Results are stored (rather than ignored) precisely so the round trip can be
    asserted from a shell: `debug_task.delay().get(timeout=10)`.
    """
    return f"celery is alive on {self.request.hostname}"
