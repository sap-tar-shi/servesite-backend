from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.utils import timezone

# Grace period after a subscription goes "halted" before we suspend the
# tenant. Configurable so it can be tuned without a code change.
DUNNING_GRACE_DAYS = getattr(settings, "BILLING_DUNNING_GRACE_DAYS", 3)


@shared_task
def check_dunning_suspensions():
    """
    Periodic task (see CELERY_BEAT_SCHEDULE). Finds subscriptions halted
    longer than the grace period and suspends the owning tenant. Runs as
    an UnscopedManager read since this is a cross-tenant sweep - that's
    exactly what UnscopedManager is for (audited via its own log line).
    """
    from .models import Subscription
    from tenants.models import Tenant

    cutoff = timezone.now() - timedelta(days=DUNNING_GRACE_DAYS)
    overdue = Subscription.unscoped.filter(status="halted", halted_at__lte=cutoff).select_related("tenant")

    suspended_count = 0
    for sub in overdue:
        tenant = sub.tenant
        if tenant.status != Tenant.STATUS_SUSPENDED:
            tenant.status = Tenant.STATUS_SUSPENDED
            tenant.save(update_fields=["status"])
            suspended_count += 1
    return suspended_count