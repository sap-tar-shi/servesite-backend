from django.urls import path
from .views import (
    SuperAdminLoginView, SuperAdminLogoutView, SuperAdminMeView,
    TenantListCreateView, TenantDetailView, TenantSuspendView, AuditLogListView,
    PlanOversightListCreateView, PlanOversightDetailView, SubscriptionOversightListView,
    TemplateRegistryListCreateView, TemplateRegistryDetailView, TemplateVersionCreateView,
    TemplateRegistryListCreateView, TemplateRegistryDetailView, TemplateVersionCreateView,
    PlatformMetricsView,
)

urlpatterns = [
    path("login/", SuperAdminLoginView.as_view(), name="superadmin-login"),
    path("logout/", SuperAdminLogoutView.as_view(), name="superadmin-logout"),
    path("me/", SuperAdminMeView.as_view(), name="superadmin-me"),
    path("tenants/", TenantListCreateView.as_view(), name="platform-tenant-list-create"),
    path("tenants/<uuid:tenant_id>/", TenantDetailView.as_view(), name="platform-tenant-detail"),
    path("tenants/<uuid:tenant_id>/suspend/", TenantSuspendView.as_view(), name="platform-tenant-suspend"),
    path("audit-logs/", AuditLogListView.as_view(), name="platform-audit-logs"),
    path("plans/", PlanOversightListCreateView.as_view(), name="platform-plan-list-create"),
    path("plans/<uuid:plan_id>/", PlanOversightDetailView.as_view(), name="platform-plan-detail"),
    path("subscriptions/", SubscriptionOversightListView.as_view(), name="platform-subscription-oversight"),
    path("templates/", TemplateRegistryListCreateView.as_view(), name="platform-template-list-create"),
    path("templates/<uuid:template_id>/", TemplateRegistryDetailView.as_view(), name="platform-template-detail"),
    path("templates/<uuid:template_id>/versions/", TemplateVersionCreateView.as_view(), name="platform-template-version-create"),
    path("metrics/", PlatformMetricsView.as_view(), name="platform-metrics"),
]