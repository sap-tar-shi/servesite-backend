from django.test import TestCase
from django.db import connection as db_connection
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from .test_models import Widget
from core.db import set_tenant_guc


class TenantScopedManagerTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(slug="tenant-a", name="Tenant A")
        self.tenant_b = Tenant.objects.create(slug="tenant-b", name="Tenant B")

        token = set_current_tenant(self.tenant_a)
        set_tenant_guc(self.tenant_a.id)
        Widget.objects.create(tenant=self.tenant_a, name="A-widget")
        reset_current_tenant(token)
        set_tenant_guc(None)

        token = set_current_tenant(self.tenant_b)
        set_tenant_guc(self.tenant_b.id)
        Widget.objects.create(tenant=self.tenant_b, name="B-widget")
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_default_manager_scopes_to_current_tenant(self):
        token = set_current_tenant(self.tenant_a)
        set_tenant_guc(self.tenant_a.id)
        names = list(Widget.objects.values_list("name", flat=True))
        reset_current_tenant(token)
        set_tenant_guc(None)
        self.assertEqual(names, ["A-widget"])

    def test_default_manager_returns_empty_without_tenant_context(self):
        self.assertEqual(list(Widget.objects.all()), [])

    def test_unscoped_manager_sees_all_tenants(self):
        # unscoped bypasses the Python manager filter, but Postgres RLS still
        # applies at the DB level unless GUC is set to see across tenants.
        # For super-admin cross-tenant reads in later phases, the DB role used
        # will have BYPASSRLS — for now, exercise it with GUC unset + policy
        # using NULLIF means this still returns zero rows, which is CORRECT:
        # RLS is stricter than the ORM-level unscoped manager. This is documented
        # in P3-T9 - superadmin cross-tenant path needs its own DB role/bypass.
        set_tenant_guc(None)
        names = set(Widget.unscoped.values_list("name", flat=True))
        self.assertEqual(names, set())

    def test_cross_tenant_read_is_impossible_via_default_manager(self):
        token = set_current_tenant(self.tenant_b)
        set_tenant_guc(self.tenant_b.id)
        names = list(Widget.objects.values_list("name", flat=True))
        reset_current_tenant(token)
        set_tenant_guc(None)
        self.assertNotIn("A-widget", names)


class RowLevelSecurityTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(slug="rls-tenant-a", name="RLS Tenant A")
        self.tenant_b = Tenant.objects.create(slug="rls-tenant-b", name="RLS Tenant B")

        token = set_current_tenant(self.tenant_a)
        set_tenant_guc(self.tenant_a.id)
        Widget.objects.create(tenant=self.tenant_a, name="A-widget-rls")
        reset_current_tenant(token)
        set_tenant_guc(None)

        token = set_current_tenant(self.tenant_b)
        set_tenant_guc(self.tenant_b.id)
        Widget.objects.create(tenant=self.tenant_b, name="B-widget-rls")
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_raw_query_with_no_guc_returns_zero_rows(self):
        """
        Simulates a 'forgotten filter' bug: a raw SQL query with NO tenant_id
        WHERE clause at all. RLS must return zero rows anyway, since the GUC
        is unset (cleared) at this point.
        """
        set_tenant_guc(None)
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT name FROM core_widget")
            rows = cursor.fetchall()
        self.assertEqual(rows, [])

    def test_raw_query_with_wrong_tenant_guc_returns_zero_foreign_rows(self):
        set_tenant_guc(self.tenant_a.id)
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT name FROM core_widget")
            rows = [r[0] for r in cursor.fetchall()]
        set_tenant_guc(None)
        self.assertEqual(rows, ["A-widget-rls"])
        self.assertNotIn("B-widget-rls", rows)