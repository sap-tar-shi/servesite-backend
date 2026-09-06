from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from .test_models import Widget
from .isolation_testing import TwoTenantIsolationTestCase


class WidgetEndpointIsolationTests(TwoTenantIsolationTestCase):
    """
    Proves the FULL pipeline (middleware -> contextvar -> GUC -> RLS -> view)
    never leaks tenant B's data into tenant A's response, and vice versa —
    through a real HTTP request, not a direct model/manager call.
    """

    def setUp(self):
        super().setUp()
        token = set_current_tenant(self.tenant_a)
        set_tenant_guc(self.tenant_a.id)
        Widget.objects.create(tenant=self.tenant_a, name="secret-a-widget")
        reset_current_tenant(token)
        set_tenant_guc(None)

        token = set_current_tenant(self.tenant_b)
        set_tenant_guc(self.tenant_b.id)
        Widget.objects.create(tenant=self.tenant_b, name="secret-b-widget")
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_widget_list_endpoint_does_not_leak_across_tenants(self):
        self.assert_no_cross_tenant_leak(
            "/api/widgets/",
            needle_a="secret-a-widget",
            needle_b="secret-b-widget",
        )

    def test_widget_list_endpoint_returns_only_own_tenant_data(self):
        resp_a = self.client.get("/api/widgets/", HTTP_HOST=self.host_a)
        self.assertEqual(resp_a.json(), {"widgets": ["secret-a-widget"]})

        resp_b = self.client.get("/api/widgets/", HTTP_HOST=self.host_b)
        self.assertEqual(resp_b.json(), {"widgets": ["secret-b-widget"]})
