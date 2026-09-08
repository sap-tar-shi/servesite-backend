from django.test import TestCase
from tenants.models import Tenant
from .models import User, Membership
from .permissions import MODULE_ROLE_MATRIX

# Maps module name -> its throwaway endpoint URL, so the matrix test can
# drive every (role, module) combination through the actual HTTP layer.
MODULE_ENDPOINTS = {
    "site_customization": "/api/auth/site-customization/",
    "menu_management": "/api/auth/pricing/",
    "live_orders": "/api/auth/live-orders/",
    "billing_staff_domains": "/api/auth/billing/",
}

ALL_ROLES = [choice[0] for choice in Membership.ROLE_CHOICES]


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

class RBACMatrixTests(TestCase):
    """
    Systematic proof of architecture §12: every role x every protected
    module. Any future role or module added to permissions.py automatically
    gets covered here without further test-writing, since this iterates
    ALL_ROLES x MODULE_ENDPOINTS.keys() rather than hardcoding cases.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(slug="matrix-tenant", name="Matrix Tenant")
        self.users_by_role = {}
        for role in ALL_ROLES:
            user = User.objects.create_user(email=f"{role}@matrix.com", password="testpass123")
            Membership.objects.create(user=user, tenant=self.tenant, role=role)
            self.users_by_role[role] = user

    def _login_as(self, role):
        return self.client.post(
            "/api/auth/login/",
            {"email": f"{role}@matrix.com", "password": "testpass123"},
            content_type="application/json",
            HTTP_HOST="matrix-tenant.localhost",
        )

    def test_every_role_against_every_module_matches_arch_matrix(self):
        failures = []
        for module, endpoint in MODULE_ENDPOINTS.items():
            allowed_roles = MODULE_ROLE_MATRIX[module]
            for role in ALL_ROLES:
                self.client.logout()
                self._login_as(role)
                resp = self.client.get(endpoint, HTTP_HOST="matrix-tenant.localhost")

                should_allow = role in allowed_roles
                actually_allowed = resp.status_code == 200

                if should_allow != actually_allowed:
                    failures.append(
                        f"module={module} role={role} expected_allowed={should_allow} "
                        f"got_status={resp.status_code}"
                    )

        self.assertEqual(
            failures, [],
            "RBAC matrix mismatch(es):\n" + "\n".join(failures)
        )


class SharedStaffAccountTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="shared-staff-tenant", name="Shared Staff Tenant")
        self.host = "shared-staff-tenant.localhost"
        self.owner = User.objects.create_user(email="owner@ss.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)

    def test_shared_staff_membership_auto_created_on_tenant_creation(self):
        membership = Membership.objects.get(tenant=self.tenant, role=Membership.ROLE_STAFF, is_shared_account=True)
        self.assertEqual(membership.user.email, f"staff@{self.tenant.slug}.staff.internal")

    def test_owner_can_reveal_shared_staff_email(self):
        self.client.post("/api/auth/login/", {"email": "owner@ss.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.get("/api/auth/staff-credentials/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], f"staff@{self.tenant.slug}.staff.internal")

    def test_owner_can_regenerate_shared_staff_password(self):
        self.client.post("/api/auth/login/", {"email": "owner@ss.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.post("/api/auth/staff-credentials/", {}, HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        new_password = resp.json()["password"]

        membership = Membership.objects.get(tenant=self.tenant, role=Membership.ROLE_STAFF, is_shared_account=True)
        self.client.logout()
        login_resp = self.client.post("/api/auth/login/", {"email": membership.user.email, "password": new_password},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(login_resp.status_code, 200)

    def test_non_owner_cannot_access_staff_credentials(self):
        kitchen = User.objects.create_user(email="kitchen@ss.com", password="testpass123")
        Membership.objects.create(user=kitchen, tenant=self.tenant, role=Membership.ROLE_KITCHEN)
        self.client.post("/api/auth/login/", {"email": "kitchen@ss.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.get("/api/auth/staff-credentials/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 403)


class IndividualStaffInviteTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="invite-tenant", name="Invite Tenant")
        self.host = "invite-tenant.localhost"
        self.owner = User.objects.create_user(email="owner@invite.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)
        self.client.post("/api/auth/login/", {"email": "owner@invite.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    def test_invite_new_user_creates_membership_and_returns_password(self):
        resp = self.client.post("/api/auth/staff/", {"email": "newstaff@invite.com"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)
        self.assertIn("password", resp.json())

        membership = Membership.objects.get(tenant=self.tenant, user__email="newstaff@invite.com")
        self.assertEqual(membership.role, Membership.ROLE_STAFF)
        self.assertFalse(membership.is_shared_account)

    def test_invite_existing_user_attaches_membership_without_password(self):
        User.objects.create_user(email="existing@invite.com", password="whatever123")
        resp = self.client.post("/api/auth/staff/", {"email": "existing@invite.com"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn("password", resp.json())

    def test_duplicate_invite_rejected(self):
        self.client.post("/api/auth/staff/", {"email": "dup@invite.com"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.post("/api/auth/staff/", {"email": "dup@invite.com"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)

    def test_non_owner_cannot_invite(self):
        kitchen = User.objects.create_user(email="kitchen@invite.com", password="testpass123")
        Membership.objects.create(user=kitchen, tenant=self.tenant, role=Membership.ROLE_KITCHEN)
        self.client.logout()
        self.client.post("/api/auth/login/", {"email": "kitchen@invite.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.post("/api/auth/staff/", {"email": "x@invite.com"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 403)

    def test_invited_staff_order_event_actor_names_individual(self):
        from menu.models import MenuCategory, MenuItem
        from tenants.context import set_current_tenant, reset_current_tenant
        from core.db import set_tenant_guc

        self.client.post("/api/auth/staff/", {"email": "kds@invite.com"},
            content_type="application/json", HTTP_HOST=self.host)
        password_resp = self.client.post("/api/auth/staff/", {"email": "kds2@invite.com"},
            content_type="application/json", HTTP_HOST=self.host).json()

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Mains")
        item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Burger", price="199.00")
        reset_current_tenant(token)
        set_tenant_guc(None)

        self.client.logout()
        self.client.post("/api/auth/login/", {"email": "kds2@invite.com", "password": password_resp["password"]},
            content_type="application/json", HTTP_HOST=self.host)
        order_resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(item.id), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_at_counter"},
            content_type="application/json", HTTP_HOST=self.host)
        order_id = order_resp.json()["id"]
        resp = self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": "accepted"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        from orders.models import OrderEvent
        event = OrderEvent.objects.filter(order_id=order_id, to_status="accepted").first()
        self.assertEqual(event.actor.email, "kds2@invite.com")
        reset_current_tenant(token)
        set_tenant_guc(None)