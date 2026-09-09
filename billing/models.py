import uuid
from django.db import models
from core.models import TenantScopedModel


class Plan(models.Model):
    """
    Platform-wide pricing tier. NOT tenant-scoped — plans are defined by the
    platform operator and apply across all tenants, so this uses plain
    models.Model, not TenantScopedModel (see core/models.py docstring).
    """

    BILLING_INTERVAL_CHOICES = [
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_interval = models.CharField(
        max_length=10, choices=BILLING_INTERVAL_CHOICES, default="monthly"
    )
    feature_limits = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} ({self.get_billing_interval_display()})"

    def get_limit(self, key, default=None):
        """
        Convenience accessor used later by P3-T4 gating, e.g.
        plan.get_limit("max_menu_items", default=0).
        """
        return self.feature_limits.get(key, default)


# Added in P3-T2: links this row to the Plan object created on Razorpay's
# side via billing.razorpay_client.create_plan(). Populated by the
# sync_razorpay_plans command, not set by hand.
Plan.add_to_class("razorpay_plan_id", models.CharField(max_length=100, blank=True, default=""))


class Subscription(TenantScopedModel):
    """
    A tenant's SaaS billing relationship with the platform. Tenant-scoped
    (unlike Plan, which is global) since each tenant has at most one
    active Subscription. Money direction: restaurant -> platform.
    """

    STATUS_CHOICES = [
        ("created", "Created"),         # subscription created, awaiting authentication payment
        ("active", "Active"),
        ("pending", "Pending"),         # a charge failed, Razorpay is retrying
        ("halted", "Halted"),           # retries exhausted, needs manual action (P3-T3 dunning)
        ("cancelled", "Cancelled"),
        ("paused", "Paused"),
        ("completed", "Completed"),
    ]

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    razorpay_subscription_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created")
    current_period_end = models.DateTimeField(null=True, blank=True)
    mandate_status = models.CharField(max_length=30, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "billing_subscription"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="unique_active_subscription_row_per_tenant"),
        ]

    def __str__(self):
        return f"{self.tenant.slug} -> {self.plan.name} ({self.status})"



class BillingWebhookEvent(TenantScopedModel):
    """
    Idempotency ledger for platform-billing webhooks (P3-T2 part 3) - mirrors
    payments.WebhookEvent's pattern for the order-payment webhook, kept as a
    separate table since this is platform-account webhook traffic, not a
    per-tenant RazorpayConnection's.
    """

    event_id = models.CharField(max_length=150, unique=True)
    event_type = models.CharField(max_length=50)

    class Meta(TenantScopedModel.Meta):
        db_table = "billing_webhook_event"