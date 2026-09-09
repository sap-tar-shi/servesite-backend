import uuid
from django.db import models


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