import uuid
import logging
from django.db import models
from tenants.context import get_current_tenant

logger = logging.getLogger("servesite.unscoped_access")


class TenantScopedManager(models.Manager):
    """
    Default manager for every tenant-scoped model. Automatically filters
    every query to the tenant in the current request context.

    If no tenant is set in context (e.g. a management command run outside
    a request), returns an empty queryset rather than all rows — silent
    unscoped access is exactly what this layer exists to prevent.
    """

    def get_queryset(self):
        tenant = get_current_tenant()
        qs = super().get_queryset()
        if tenant is None:
            return qs.none()
        return qs.filter(tenant_id=tenant.id)


class UnscopedManager(models.Manager):
    """
    Explicit opt-out of tenant scoping. Every use is logged so cross-tenant
    reads are auditable, per architecture §4 layer 1 and §13 (super-admin
    cross-tenant metrics must go through this path only).

    Use ONLY for super-admin cross-tenant operations. Using this anywhere
    in tenant-facing code is a bug.
    """

    def get_queryset(self):
        logger.warning(
            "UNSCOPED_ACCESS model=%s", self.model.__name__
        )
        return super().get_queryset()


class TenantScopedModel(models.Model):
    """
    Abstract base for every tenant-scoped table. Provides:
    - tenant FK (tenant_id column), indexed.
    - `objects`: tenant-scoped default manager (opt-out, not opt-in).
    - `unscoped`: explicit, logged escape hatch.
    - created_at, for the (tenant_id, created_at) composite index convention
      used by nearly every tenant-scoped query (architecture §4).

    Concrete subclasses should extend Meta.indexes rather than replace it,
    e.g.:

        class Meta(TenantScopedModel.Meta):
            indexes = TenantScopedModel.Meta.indexes + [
                models.Index(fields=["tenant", "status"]),
            ]
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, db_index=False  # index provided via Meta.indexes below, not db_index
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedManager()
    unscoped = UnscopedManager()

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
        ]


from .test_models import Widget  # noqa: F401  (test-only model, see P1-T4)