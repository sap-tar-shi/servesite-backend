from .models import TenantScopedModel
from django.db import models


class Widget(TenantScopedModel):
    """Throwaway model used only to exercise TenantScopedModel in tests."""

    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="active")

    class Meta(TenantScopedModel.Meta):
        indexes = TenantScopedModel.Meta.indexes + [
            models.Index(fields=["tenant", "status"]),
        ]
