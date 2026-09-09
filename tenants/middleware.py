from django.http import Http404
from .context import set_current_tenant, reset_current_tenant
from .models import Tenant
from core.db import set_tenant_guc

# Hosts that are never tenant subdomains — platform-level surfaces.
# Extend this as super-admin / marketing domains are added (P3-T5, P4-T4).
RESERVED_HOSTS = {"localhost", "127.0.0.1", "platform.com", "www.platform.com", "admin.platform.com", "admin.localhost"}


def resolve_slug_from_host(host: str):
    """
    Extracts a tenant slug from a Host header of the form
    '{slug}.platform.com' or '{slug}.localhost' (for local dev).
    Returns None if the host isn't a tenant-subdomain shape.
    """
    host = host.split(":")[0]  # strip port, e.g. localhost:8000
    if host in RESERVED_HOSTS:
        return None

    parts = host.split(".")
    if len(parts) < 2:
        return None

    # {slug}.localhost  (local dev)  or  {slug}.platform.com  (prod)
    return parts[0]


class TenantContextMiddleware:
    """
    Resolves the current tenant from the request Host header and sets it in
    an async-safe contextvars.ContextVar for the duration of the request.
    Always clears the context afterward, even on exceptions.

    Unknown/unresolvable tenant slugs raise Http404 rather than silently
    falling through to an unscoped state — per architecture §4/§5.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        slug = resolve_slug_from_host(request.get_host())

        tenant = None
        if slug is not None:
            try:
                tenant = Tenant.objects.get(slug=slug)
            except Tenant.DoesNotExist:
                raise Http404(f"No tenant found for slug '{slug}'")

        request.tenant = tenant
        token = set_current_tenant(tenant)
        set_tenant_guc(tenant.id if tenant else None)
        try:
            response = self.get_response(request)
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)  # clear so the next request on this connection starts clean
        return response
