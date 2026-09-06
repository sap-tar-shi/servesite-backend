from django.db import connection


def set_tenant_guc(tenant_id):
    """
    Sets the session-local Postgres GUC used by RLS policies.

    NOTE on scope: `local=false` here (session-scoped, not transaction-scoped)
    because local dev has no PgBouncer in front (see docs/deferred-to-prod.md).
    Production, once PgBouncer transaction-pooling is enabled (P0-T3 deferred item),
    MUST re-verify this against `local=true` per-transaction — a connection may be
    handed to a different tenant's request between transactions under pooling.
    This function's signature doesn't need to change; only the `local` flag does,
    and that switch is a one-line change gated on the PgBouncer spike (Implementation
    Plan §9, spike #2).
    """
    with connection.cursor() as cursor:
        if tenant_id is None:
            cursor.execute("SELECT set_config('app.current_tenant', '', false)")
        else:
            cursor.execute("SELECT set_config('app.current_tenant', %s, false)", [str(tenant_id)])