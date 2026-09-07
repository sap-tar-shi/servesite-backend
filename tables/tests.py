from django.test import TestCase
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from core.isolation_testing import TwoTenantIsolationTestCase
from accounts.models import User, Membership
from .models import Table


class TableIsolationTests(TwoTenantIsolationTestCase):
    def setUp(self):
        super().setUp()
        for tenant, label in [(self.tenant_a, "A's Secret Table"), (self.tenant_b, "B's Secret Table")]:
            token = set_current_tenant(tenant)
            set_tenant_guc(tenant.id)
            Table.objects.create(tenant=tenant, label=label)
            reset_current_tenant(token)
            set_tenant_guc(None)
        for tenant, email in [(self.tenant_a, "owner-a@tbl.com"), (self.tenant_b, "owner-b@tbl.com")]:
            user = User.objects.create_user(email=email, password="testpass123")
            Membership.objects.create(user=user, tenant=tenant, role=Membership.ROLE_OWNER)

    def _login(self, email, host):
        return self.client.post("/api/auth/login/", {"email": email, "password": "testpass123"},
            content_type="application/json", HTTP_HOST=host)

    def test_tables_do_not_leak_across_tenants(self):
        self._login("owner-a@tbl.com", self.host_a)
        resp = self.client.get("/api/tables/", HTTP_HOST=self.host_a)
        body = resp.content.decode()
        self.assertIn("A's Secret Table", body)
        self.assertNotIn("B's Secret Table", body)


class TableRBACAndBehaviorTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="tables-tenant", name="Tables Tenant")
        self.host = "tables-tenant.localhost"
        self.owner = User.objects.create_user(email="owner@tables.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)
        self.staff = User.objects.create_user(email="staff@tables.com", password="testpass123")
        Membership.objects.create(user=self.staff, tenant=self.tenant, role=Membership.ROLE_STAFF)

    def _login(self, email):
        return self.client.post("/api/auth/login/", {"email": email, "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    def test_owner_can_create_table(self):
        self._login("owner@tables.com")
        resp = self.client.post("/api/tables/", {"label": "Table 1"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(len(resp.json()["table_token"]) > 20)

    def test_staff_cannot_create_table(self):
        self._login("staff@tables.com")
        resp = self.client.post("/api/tables/", {"label": "Table 1"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 403)

    def test_rotate_token_changes_value(self):
        self._login("owner@tables.com")
        create_resp = self.client.post("/api/tables/", {"label": "Table 2"},
            content_type="application/json", HTTP_HOST=self.host)
        table_id = create_resp.json()["id"]
        old_token = create_resp.json()["table_token"]

        rotate_resp = self.client.post(f"/api/tables/{table_id}/rotate-token/", HTTP_HOST=self.host)
        self.assertEqual(rotate_resp.status_code, 200)
        self.assertNotEqual(rotate_resp.json()["table_token"], old_token)

    def test_qr_endpoint_returns_png(self):
        self._login("owner@tables.com")
        create_resp = self.client.post("/api/tables/", {"label": "Table 3"},
            content_type="application/json", HTTP_HOST=self.host)
        table_id = create_resp.json()["id"]

        qr_resp = self.client.get(f"/api/tables/{table_id}/qr/", HTTP_HOST=self.host)
        self.assertEqual(qr_resp.status_code, 200)
        self.assertEqual(qr_resp["Content-Type"], "image/png")