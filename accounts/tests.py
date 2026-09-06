from django.test import TestCase
from tenants.models import Tenant
from .models import User, Membership


class CrossSubdomainSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="owner@example.com", password="testpass123")
        Tenant.objects.create(slug="tenant-a", name="Tenant A")
        Tenant.objects.create(slug="tenant-b", name="Tenant B")

    def test_login_then_me_works_on_different_subdomain(self):
        login_resp = self.client.post(
            "/api/auth/login/",
            {"email": "owner@example.com", "password": "testpass123"},
            content_type="application/json",
            HTTP_HOST="tenant-a.localhost",
        )
        self.assertEqual(login_resp.status_code, 200)

        me_resp = self.client.get("/api/auth/me/", HTTP_HOST="tenant-b.localhost")
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["email"], "owner@example.com")

    def test_unauthenticated_me_returns_401(self):
        resp = self.client.get("/api/auth/me/", HTTP_HOST="tenant-a.localhost")
        self.assertEqual(resp.status_code, 401)

class MembershipTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="multi@example.com", password="testpass123")
        self.tenant_a = Tenant.objects.create(slug="multi-a", name="Multi A")
        self.tenant_b = Tenant.objects.create(slug="multi-b", name="Multi B")
        Membership.objects.create(user=self.user, tenant=self.tenant_a, role=Membership.ROLE_OWNER)
        Membership.objects.create(user=self.user, tenant=self.tenant_b, role=Membership.ROLE_MANAGER)

    def test_user_can_hold_memberships_in_multiple_tenants(self):
        memberships = Membership.objects.filter(user=self.user)
        self.assertEqual(memberships.count(), 2)

    def test_login_resolves_all_memberships(self):
        login_resp = self.client.post(
            "/api/auth/login/",
            {"email": "multi@example.com", "password": "testpass123"},
            content_type="application/json",
            HTTP_HOST="multi-a.localhost",
        )
        self.assertEqual(login_resp.status_code, 200)
        memberships = login_resp.json()["memberships"]
        self.assertEqual(len(memberships), 2)
        roles = {m["tenant_slug"]: m["role"] for m in memberships}
        self.assertEqual(roles["multi-a"], "owner")
        self.assertEqual(roles["multi-b"], "manager")

    def test_duplicate_membership_same_user_tenant_rejected(self):
        with self.assertRaises(Exception):
            Membership.objects.create(user=self.user, tenant=self.tenant_a, role=Membership.ROLE_STAFF)

class RBACEnforcementTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="rbac-tenant", name="RBAC Tenant")

        self.owner = User.objects.create_user(email="owner@rbac.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)

        self.staff = User.objects.create_user(email="staff@rbac.com", password="testpass123")
        Membership.objects.create(user=self.staff, tenant=self.tenant, role=Membership.ROLE_STAFF)

    def _login(self, email, password):
        return self.client.post(
            "/api/auth/login/",
            {"email": email, "password": password},
            content_type="application/json",
            HTTP_HOST="rbac-tenant.localhost",
        )

    def test_staff_role_gets_403_on_pricing_endpoint(self):
        self._login("staff@rbac.com", "testpass123")
        resp = self.client.get("/api/auth/pricing/", HTTP_HOST="rbac-tenant.localhost")
        self.assertEqual(resp.status_code, 403)

    def test_owner_role_gets_200_on_pricing_endpoint(self):
        self._login("owner@rbac.com", "testpass123")
        resp = self.client.get("/api/auth/pricing/", HTTP_HOST="rbac-tenant.localhost")
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_gets_403_on_pricing_endpoint(self):
        resp = self.client.get("/api/auth/pricing/", HTTP_HOST="rbac-tenant.localhost")
        self.assertEqual(resp.status_code, 403)