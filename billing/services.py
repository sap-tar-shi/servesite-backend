from .models import Plan, Subscription


def get_effective_plan(tenant):
    """
    Returns the Plan whose feature_limits currently govern this tenant:
    - an active/created Subscription's plan, if one exists
    - otherwise the cheapest active Plan, as the trial-period default
      (deliberate choice - see P3-T4 checkpoint note; trial tenants are
      capped at Starter-tier limits, not unlimited)
    Returns None only if no Plan rows exist at all (misconfigured platform).
    """
    sub = Subscription.objects.filter(
        tenant=tenant, status__in=["created", "active", "pending"]
    ).select_related("plan").first()
    if sub:
        return sub.plan
    return Plan.objects.filter(is_active=True).order_by("price").first()


class FeatureLimitExceeded(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


def enforce_count_limit(tenant, *, limit_key, current_count, item_label):
    """
    Raises FeatureLimitExceeded if current_count >= the tenant's effective
    plan limit for limit_key. Callers check this BEFORE creating the new
    row (current_count = count before insert).
    """
    plan = get_effective_plan(tenant)
    if plan is None:
        return  # no plans configured at all - fail open rather than lock out every tenant
    limit = plan.get_limit(limit_key)
    if limit is None:
        return  # key not present in this plan's feature_limits - no cap defined
    if current_count >= limit:
        raise FeatureLimitExceeded(
            f"Your current plan ({plan.name}) allows up to {limit} {item_label}. "
            f"Upgrade your plan to add more."
        )


def enforce_bool_flag(tenant, *, limit_key, feature_label):
    plan = get_effective_plan(tenant)
    if plan is None:
        return
    if not plan.get_limit(limit_key, default=False):
        raise FeatureLimitExceeded(
            f"{feature_label} is not available on your current plan ({plan.name}). Upgrade to enable it."
        )