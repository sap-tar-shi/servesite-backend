import threading
from django.test import TestCase, Client
from .context import set_current_tenant, get_current_tenant, reset_current_tenant
from .models import Tenant


class TenantContextIsolationTests(TestCase):
    def test_set_get_reset_roundtrip(self):
        self.assertIsNone(get_current_tenant())
        token = set_current_tenant("tenant-A")
        self.assertEqual(get_current_tenant(), "tenant-A")
        reset_current_tenant(token)
        self.assertIsNone(get_current_tenant())

    def test_no_bleed_across_concurrent_threads(self):
        """
        Simulates two 'requests' running concurrently on different threads.
        Each sets its own tenant context; neither should ever observe the
        other's value. This is the core guarantee P1-T2's AC requires.
        """
        results = {}

        def worker(tenant_id, barrier):
            token = set_current_tenant(tenant_id)
            barrier.wait()  # force overlap: both threads are "in-request" at once
            results[tenant_id] = get_current_tenant()
            reset_current_tenant(token)

        barrier = threading.Barrier(2)
        t1 = threading.Thread(target=worker, args=("tenant-A", barrier))
        t2 = threading.Thread(target=worker, args=("tenant-B", barrier))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results["tenant-A"], "tenant-A")
        self.assertEqual(results["tenant-B"], "tenant-B")
    

class TenantResolutionMiddlewareTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="acme-diner", name="Acme Diner")

    def test_known_subdomain_resolves_tenant(self):
        response = self.client.get("/admin/login/", HTTP_HOST="acme-diner.localhost")
        self.assertEqual(response.status_code, 200)

    def test_unknown_subdomain_returns_404(self):
        response = self.client.get("/admin/login/", HTTP_HOST="ghost-tenant.localhost")
        self.assertEqual(response.status_code, 404)

    def test_reserved_host_has_no_tenant(self):
        response = self.client.get("/admin/login/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)