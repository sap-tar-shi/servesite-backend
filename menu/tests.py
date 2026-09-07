from django.test import TestCase
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from core.isolation_testing import TwoTenantIsolationTestCase
from accounts.models import User, Membership
from .models import MenuCategory, MenuItem
from unittest.mock import patch


class MenuIsolationTests(TwoTenantIsolationTestCase):
    def setUp(self):
        super().setUp()
        for tenant, secret in [(self.tenant_a, "Tenant A Secret Dish"), (self.tenant_b, "Tenant B Secret Dish")]:
            token = set_current_tenant(tenant)
            set_tenant_guc(tenant.id)
            category = MenuCategory.objects.create(tenant=tenant, name="Mains")
            MenuItem.objects.create(tenant=tenant, category=category, name=secret, price="100.00")
            reset_current_tenant(token)
            set_tenant_guc(None)

        for tenant, email in [(self.tenant_a, "owner-a@iso.com"), (self.tenant_b, "owner-b@iso.com")]:
            user = User.objects.create_user(email=email, password="testpass123")
            Membership.objects.create(user=user, tenant=tenant, role=Membership.ROLE_OWNER)

    def _login(self, email, host):
        return self.client.post("/api/auth/login/", {"email": email, "password": "testpass123"},
            content_type="application/json", HTTP_HOST=host)

    def test_menu_items_do_not_leak_across_tenants(self):
        self._login("owner-a@iso.com", self.host_a)
        resp_a = self.client.get("/api/menu/items/", HTTP_HOST=self.host_a)
        self.client.logout()
        self._login("owner-b@iso.com", self.host_b)
        resp_b = self.client.get("/api/menu/items/", HTTP_HOST=self.host_b)

        body_a, body_b = resp_a.content.decode(), resp_b.content.decode()
        self.assertIn("Tenant A Secret Dish", body_a)
        self.assertNotIn("Tenant B Secret Dish", body_a)
        self.assertIn("Tenant B Secret Dish", body_b)
        self.assertNotIn("Tenant A Secret Dish", body_b)

    def test_item_detail_of_other_tenant_is_404_not_403(self):
        token = set_current_tenant(self.tenant_b)
        set_tenant_guc(self.tenant_b.id)
        other_item = MenuItem.objects.get(name="Tenant B Secret Dish")
        reset_current_tenant(token)
        set_tenant_guc(None)

        self._login("owner-a@iso.com", self.host_a)
        resp = self.client.get(f"/api/menu/items/{other_item.id}/", HTTP_HOST=self.host_a)
        self.assertEqual(resp.status_code, 404)


class MenuRBACTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="menu-rbac-tenant", name="Menu RBAC Tenant")
        self.host = "menu-rbac-tenant.localhost"

        self.owner = User.objects.create_user(email="owner@menurbac.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)
        self.manager = User.objects.create_user(email="manager@menurbac.com", password="testpass123")
        Membership.objects.create(user=self.manager, tenant=self.tenant, role=Membership.ROLE_MANAGER)
        self.staff = User.objects.create_user(email="staff@menurbac.com", password="testpass123")
        Membership.objects.create(user=self.staff, tenant=self.tenant, role=Membership.ROLE_STAFF)

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Mains")
        reset_current_tenant(token)
        set_tenant_guc(None)

    def _login(self, email):
        return self.client.post("/api/auth/login/", {"email": email, "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    def test_owner_can_create_category(self):
        self._login("owner@menurbac.com")
        resp = self.client.post("/api/menu/categories/", {"name": "Desserts"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)

    def test_manager_can_create_item(self):
        self._login("manager@menurbac.com")
        resp = self.client.post("/api/menu/items/",
            {"category": str(self.category.id), "name": "Pasta", "price": "199.00"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)

    def test_staff_cannot_create_category(self):
        self._login("staff@menurbac.com")
        resp = self.client.post("/api/menu/categories/", {"name": "Desserts"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 403)

    def test_staff_cannot_list_items(self):
        self._login("staff@menurbac.com")
        resp = self.client.get("/api/menu/items/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 403)

    def test_staff_cannot_toggle_availability(self):
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        item = MenuItem.objects.create(tenant=self.tenant, category=self.category, name="Soup", price="99.00")
        reset_current_tenant(token)
        set_tenant_guc(None)

        self._login("staff@menurbac.com")
        resp = self.client.patch(f"/api/menu/items/{item.id}/", {"is_available": False},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 403)


class MenuCRUDTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="menu-crud-tenant", name="Menu CRUD Tenant")
        self.host = "menu-crud-tenant.localhost"
        self.owner = User.objects.create_user(email="owner@menucrud.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)
        self.client.post("/api/auth/login/", {"email": "owner@menucrud.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    def test_category_and_item_lifecycle(self):
        resp = self.client.post("/api/menu/categories/", {"name": "Starters", "ordered_position": 0},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)
        category_id = resp.json()["id"]

        resp = self.client.post("/api/menu/items/",
            {"category": category_id, "name": "Bruschetta", "price": "149.00", "description": "Classic."},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)
        item_id = resp.json()["id"]
        self.assertTrue(resp.json()["is_available"])

        resp = self.client.patch(f"/api/menu/items/{item_id}/", {"is_available": False},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_available"])

        resp = self.client.get(f"/api/menu/categories/{category_id}/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["items"]), 1)

        resp = self.client.delete(f"/api/menu/items/{item_id}/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 204)

    def test_duplicate_category_name_rejected(self):
        self.client.post("/api/menu/categories/", {"name": "Mains"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.post("/api/menu/categories/", {"name": "Mains"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)


class PublicMenuViewTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="public-menu-tenant", name="Public Menu Tenant")
        self.host = "public-menu-tenant.localhost"
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        visible_cat = MenuCategory.objects.create(tenant=self.tenant, name="Mains", visible=True)
        MenuItem.objects.create(tenant=self.tenant, category=visible_cat, name="Pizza", price="199.00", is_available=True)
        MenuItem.objects.create(tenant=self.tenant, category=visible_cat, name="Sold Out Item", price="99.00", is_available=False)
        MenuCategory.objects.create(tenant=self.tenant, name="Hidden Seasonal", visible=False)
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_public_endpoint_requires_no_auth(self):
        resp = self.client.get("/api/menu/public/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)

    def test_hidden_category_excluded(self):
        resp = self.client.get("/api/menu/public/", HTTP_HOST=self.host)
        names = [c["name"] for c in resp.json()]
        self.assertIn("Mains", names)
        self.assertNotIn("Hidden Seasonal", names)

    def test_unavailable_item_still_included_but_flagged(self):
        resp = self.client.get("/api/menu/public/", HTTP_HOST=self.host)
        items = resp.json()[0]["items"]
        sold_out = next(i for i in items if i["name"] == "Sold Out Item")
        self.assertFalse(sold_out["is_available"])


class MenuRevalidationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="revalidate-tenant", name="Revalidate Tenant")
        self.host = "revalidate-tenant.localhost"
        self.owner = User.objects.create_user(email="owner@revalidate.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)
        self.client.post("/api/auth/login/", {"email": "owner@revalidate.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    @patch("menu.views.revalidate_public_menu.delay")
    def test_category_create_triggers_revalidation(self, mock_task):
        resp = self.client.post("/api/menu/categories/", {"name": "Mains"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)
        mock_task.assert_called_once_with("revalidate-tenant")

    @patch("menu.views.revalidate_public_menu.delay")
    def test_item_availability_toggle_triggers_revalidation(self, mock_task):
        cat_resp = self.client.post("/api/menu/categories/", {"name": "Mains"},
            content_type="application/json", HTTP_HOST=self.host)
        category_id = cat_resp.json()["id"]
        mock_task.reset_mock()

        item_resp = self.client.post("/api/menu/items/",
            {"category": category_id, "name": "Soup", "price": "99.00"},
            content_type="application/json", HTTP_HOST=self.host)
        item_id = item_resp.json()["id"]
        mock_task.reset_mock()

        resp = self.client.patch(f"/api/menu/items/{item_id}/", {"is_available": False},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        mock_task.assert_called_once_with("revalidate-tenant")