from django.db import connection


def set_tenant_guc(tenant_id):
    """
    Sets the session-local Postgres GUC used by RLS policies.
    Must be called inside the same transaction/connection that will
    run the tenant-scoped queries — call this from middleware, per request,
    after the transaction has begun.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_tenant', %s, true)", [str(tenant_id)])
        #                                                        ^ true = transaction-scoped, not session-scoped