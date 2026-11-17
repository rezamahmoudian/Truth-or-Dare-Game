from celery import shared_task


@shared_task(ignore_result=True)
def process_payment(attempt_id):
    from .payments import run_checkout
    run_checkout(attempt_id)


@shared_task(ignore_result=True)
def recover_payments():
    from .payments import reconcile_payments
    return reconcile_payments()


@shared_task(ignore_result=True)
def refresh_vip_boundaries():
    """Best-effort live decoration updates; API reads remain authoritative."""
    from datetime import timedelta
    from django.db.models import Q
    from django.utils import timezone
    from .models import VIPSubscription
    from .vip import notify_change
    now = timezone.now()
    since = now - timedelta(minutes=2)
    ids = VIPSubscription.objects.filter(
        Q(starts_at__gt=since, starts_at__lte=now) | Q(ends_at__gt=since, ends_at__lte=now)
    ).values_list("user_id", flat=True).distinct()
    for user_id in ids.iterator(chunk_size=100):
        notify_change(user_id)
