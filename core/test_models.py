from .models import TenantScopedModel
from django.db import models


class Widget(TenantScopedModel):
    """Throwaway model used only to exercise TenantScopedModel in tests."""

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "core"