import uuid
from django.db import models


class Tenant(models.Model):
    STATUS_TRIAL = "trial"
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_CHOICES = [
        (STATUS_TRIAL, "Trial"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
    ]

    STAFF_MODE_SHARED = "shared"
    STAFF_MODE_INDIVIDUAL = "individual"
    STAFF_MODE_CHOICES = [
        (STAFF_MODE_SHARED, "Shared"),
        (STAFF_MODE_INDIVIDUAL, "Individual"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=63)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRIAL)
    staff_account_mode = models.CharField(max_length=20, choices=STAFF_MODE_CHOICES, default=STAFF_MODE_SHARED)
    online_payment_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_tenant"

    def __str__(self):
        return f"{self.name} ({self.slug})"
