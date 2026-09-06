from django.test import TestCase
from tenants.models import Tenant


class TwoTenantIsolationTestCase(TestCase):
    """
    Base class for isolation tests. Every future app (menu, CMS, orders, etc.)
    that adds tenant-scoped endpoints should subclass this and add a
    `test_<endpoint>_does_not_leak_across_tenants` method per endpoint,
    per architecture §4 layer 4 / Implementation Plan P1-T7.

    Provides two seeded tenants (self.tenant_a, self.tenant_b) with distinct
    subdomains, ready to use as HTTP_HOST in client requests:

        response = self.client.get("/api/menu/", HTTP_HOST=self.host_a)
    """

    def setUp(self):
        super().setUp()
        self.tenant_a = Tenant.objects.create(slug="iso-tenant-a", name="Iso Tenant A")
        self.tenant_b = Tenant.objects.create(slug="iso-tenant-b", name="Iso Tenant B")
        self.host_a = "iso-tenant-a.localhost"
        self.host_b = "iso-tenant-b.localhost"

    def assert_no_cross_tenant_leak(self, path, needle_a, needle_b):
        """
        Hits `path` as tenant A and tenant B, asserting each response contains
        only its own tenant's marker string and never the other's.
        """
        resp_a = self.client.get(path, HTTP_HOST=self.host_a)
        resp_b = self.client.get(path, HTTP_HOST=self.host_b)

        body_a = resp_a.content.decode()
        body_b = resp_b.content.decode()

        assert needle_b not in body_a, f"Tenant A response leaked tenant B data at {path}"
        assert needle_a not in body_b, f"Tenant B response leaked tenant A data at {path}"