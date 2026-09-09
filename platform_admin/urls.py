from django.urls import path
from .views import (
    SuperAdminLoginView, SuperAdminLogoutView, SuperAdminMeView,
    TenantListCreateView, TenantDetailView, TenantSuspendView, AuditLogListView,
)

urlpatterns = [
    path("login/", SuperAdminLoginView.as_view(), name="superadmin-login"),
    path("logout/", SuperAdminLogoutView.as_view(), name="superadmin-logout"),
    path("me/", SuperAdminMeView.as_view(), name="superadmin-me"),
    path("tenants/", TenantListCreateView.as_view(), name="platform-tenant-list-create"),
    path("tenants/<uuid:tenant_id>/", TenantDetailView.as_view(), name="platform-tenant-detail"),
    path("tenants/<uuid:tenant_id>/suspend/", TenantSuspendView.as_view(), name="platform-tenant-suspend"),
    path("audit-logs/", AuditLogListView.as_view(), name="platform-audit-logs"),
]