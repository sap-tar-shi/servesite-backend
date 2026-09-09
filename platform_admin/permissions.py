from django.conf import settings
from rest_framework.permissions import BasePermission


def _client_ip(request):
    # Deferred to prod: this trusts REMOTE_ADDR directly, which is wrong
    # once a real reverse proxy/load balancer sits in front (needs
    # X-Forwarded-For parsing against a trusted proxy list instead).
    return request.META.get("REMOTE_ADDR", "")


class IsPlatformAdminOrigin(BasePermission):
    """
    Enforces BOTH conditions for every super-admin endpoint:
    1. Request host is exactly the configured platform-admin origin -
       hitting these views from a tenant subdomain or the main site 403s,
       regardless of who's authenticated.
    2. If PLATFORM_ADMIN_ALLOWED_IPS is configured, client IP must be in
       that allowlist (empty list = no IP restriction, dev-friendly).
    """

    message = "This origin is not permitted to access the platform-admin API."

    def has_permission(self, request, view):
        host = request.get_host().split(":")[0]
        if host != settings.PLATFORM_ADMIN_HOST:
            return False

        allowed_ips = [ip.strip() for ip in settings.PLATFORM_ADMIN_ALLOWED_IPS.split(",") if ip.strip()]
        if allowed_ips and _client_ip(request) not in allowed_ips:
            return False

        return True


class IsSuperAdminAuthenticated(IsPlatformAdminOrigin):
    """Origin checks above, PLUS a logged-in SuperAdmin (request.superadmin)."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return getattr(request, "superadmin", None) is not None