from rest_framework.permissions import BasePermission
from tenants.models import Tenant


class TenantNotSuspended(BasePermission):
    """
    Blocks diner-facing endpoints (public menu, cart, checkout, payment)
    when the tenant is suspended (billing non-payment, P3-T3). Admin
    (/manage) endpoints deliberately do NOT use this - an owner must still
    be able to log in and view/fix their billing while suspended.
    """

    message = "This restaurant's site is temporarily unavailable."

    def has_permission(self, request, view):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return True  # no tenant context resolved - not this permission's concern
        return tenant.status != Tenant.STATUS_SUSPENDED