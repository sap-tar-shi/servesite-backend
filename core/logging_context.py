import contextvars

# Populated by tenant-resolution middleware in Phase 1 (P1-T2/T3).
# Defaults to "none" for any request/process that hasn't set it yet
# (e.g. management commands, pre-Phase-1 code, Celery tasks without tenant context).
current_tenant_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_tenant_id", default="none")


class TenantLogFilter:
    """
    Injects tenant_id into every LogRecord so structured logs are
    tenant-taggable from day one, per architecture §14.
    """

    def filter(self, record):
        record.tenant_id = current_tenant_id.get()
        return True
