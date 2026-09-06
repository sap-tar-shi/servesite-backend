from rest_framework.permissions import BasePermission
from .models import Membership


# Central permission matrix - mirrors architecture §12 exactly.
# Extend this dict as new modules are added in later phases; never
# hardcode role checks ad-hoc in individual views.
MODULE_ROLE_MATRIX = {
    "site_customization": {Membership.ROLE_OWNER},
    "menu_management": {Membership.ROLE_OWNER, Membership.ROLE_MANAGER},
    "live_orders": {Membership.ROLE_OWNER, Membership.ROLE_MANAGER, Membership.ROLE_KITCHEN, Membership.ROLE_WAITER, Membership.ROLE_STAFF},
    "billing_staff_domains": {Membership.ROLE_OWNER},
}


def get_membership_for_request(request):
    """
    Returns the Membership linking request.user to request.tenant, or None
    if the user is unauthenticated, no tenant is resolved, or the user has
    no membership at this tenant.
    """
    if not request.user.is_authenticated:
        return None
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return None
    return Membership.objects.filter(user=request.user, tenant=tenant).first()


class HasTenantRole(BasePermission):
    """
    DRF permission class factory. Usage on a view:

        class MenuItemView(APIView):
            permission_classes = [HasModulePermission("menu_management")]

    Enforces per architecture §12: a crafted request from a role outside
    the matrix for this module returns 403, regardless of what the
    frontend shows or hides.
    """

    module = None  # set by HasModulePermission()

    def has_permission(self, request, view):
        membership = get_membership_for_request(request)
        if membership is None:
            return False
        allowed_roles = MODULE_ROLE_MATRIX.get(self.module, set())
        return membership.role in allowed_roles


def HasModulePermission(module_name):
    """Factory returning a HasTenantRole subclass bound to a specific module."""
    return type(
        f"HasModulePermission_{module_name}",
        (HasTenantRole,),
        {"module": module_name},
    )

class HasAnyMembershipInTenant(BasePermission):
    """
    Rejects any authenticated request whose tenant context doesn't match
    ANY membership the user holds - i.e. blocks a user from acting on a
    tenant they have zero relationship with, independent of role.
    Use this on endpoints that don't need a specific role, just tenant
    membership of any kind (rare - most endpoints should use
    HasModulePermission instead, which already implies this check).
    """

    def has_permission(self, request, view):
        return get_membership_for_request(request) is not None