from .context import set_current_tenant, reset_current_tenant


class TenantContextMiddleware:
    """
    Sets the current-tenant context for the duration of one request, then
    always clears it afterward — even on exceptions — so nothing can bleed
    into a request handled by the same worker afterward.

    P1-T2 scope: prove the set/reset lifecycle is airtight.
    P1-T3 will replace the placeholder `tenant = None` below with real
    Host-header -> slug -> Tenant resolution.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = None  # placeholder; P1-T3 resolves this from request.get_host()
        token = set_current_tenant(tenant)
        try:
            response = self.get_response(request)
        finally:
            reset_current_tenant(token)
        return response