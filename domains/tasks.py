from celery import shared_task
from django.utils import timezone
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from .models import Domain
from .aws_client import describe_certificate, attach_certificate_to_distribution


def _activate_domain(domain):
    """Shared by both tasks below - attaches the issued cert to CloudFront
    and flips the domain to active. Runs inside the tenant context set by
    the caller."""
    attach_certificate_to_distribution(domain.acm_certificate_arn, domain.hostname)
    domain.status = Domain.STATUS_ACTIVE
    domain.activated_at = timezone.now()
    domain.save(update_fields=["status", "activated_at"])


def _check_and_advance(domain):
    """
    Polls ACM for one domain's cert status and advances/fails it
    accordingly. Tenant-scoped writes require the tenant context to be
    set first (P1-T2) - caller is responsible for that, since this
    function is shared between the single-domain task (context set by the
    caller who already has request.tenant) and the periodic sweep
    (context set per-row below, since it's cross-tenant).
    """
    description = describe_certificate(domain.acm_certificate_arn)["Certificate"]
    acm_status = description["Status"]

    if acm_status == "ISSUED":
        _activate_domain(domain)
    elif acm_status == "FAILED":
        domain.status = Domain.STATUS_FAILED
        domain.failure_reason = description.get("FailureReason", "ACM certificate validation failed.")
        domain.save(update_fields=["status", "failure_reason"])
    # else: still PENDING_VALIDATION - no-op, next poll will check again


@shared_task
def poll_single_domain_verification(domain_id):
    """
    Fired once, right after DomainVerifyView successfully requests a cert -
    gives a fast first check instead of waiting for the next periodic
    sweep. If ACM hasn't issued yet, the periodic task below picks up from
    here on subsequent runs.
    """
    domain = Domain.unscoped.select_related("tenant").get(id=domain_id)
    token = set_current_tenant(domain.tenant)
    set_tenant_guc(domain.tenant.id)
    try:
        _check_and_advance(domain)
    finally:
        reset_current_tenant(token)
        set_tenant_guc(None)


@shared_task
def poll_pending_domain_verifications():
    """
    Periodic task (see CELERY_BEAT_SCHEDULE, every 5 min). Cross-tenant
    sweep of every domain still mid-issuance - deliberate use of
    Domain.unscoped, same pattern as billing.tasks.check_dunning_suspensions.
    """
    pending = Domain.unscoped.filter(status=Domain.STATUS_ISSUING_CERT).select_related("tenant")
    checked = 0
    for domain in pending:
        token = set_current_tenant(domain.tenant)
        set_tenant_guc(domain.tenant.id)
        try:
            _check_and_advance(domain)
            checked += 1
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)
    return checked