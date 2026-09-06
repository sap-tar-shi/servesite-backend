from django.test import TestCase
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from .test_models import Widget


class TenantScopedManagerTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(slug="tenant-a", name="Tenant A")
        self.tenant_b = Tenant.objects.create(slug="tenant-b", name="Tenant B")

        token = set_current_tenant(self.tenant_a)
        Widget.objects.create(tenant=self.tenant_a, name="A-widget")
        reset_current_tenant(token)

        token = set_current_tenant(self.tenant_b)
        Widget.objects.create(tenant=self.tenant_b, name="B-widget")
        reset_current_tenant(token)

    def test_default_manager_scopes_to_current_tenant(self):
        token = set_current_tenant(self.tenant_a)
        names = list(Widget.objects.values_list("name", flat=True))
        reset_current_tenant(token)
        self.assertEqual(names, ["A-widget"])

    def test_default_manager_returns_empty_without_tenant_context(self):
        # No set_current_tenant called - context defaults to None.
        self.assertEqual(list(Widget.objects.all()), [])

    def test_unscoped_manager_sees_all_tenants(self):
        names = set(Widget.unscoped.values_list("name", flat=True))
        self.assertEqual(names, {"A-widget", "B-widget"})

    def test_cross_tenant_read_is_impossible_via_default_manager(self):
        token = set_current_tenant(self.tenant_b)
        names = list(Widget.objects.values_list("name", flat=True))
        reset_current_tenant(token)
        self.assertNotIn("A-widget", names)