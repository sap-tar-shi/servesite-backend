from django.test import TestCase
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from menu.models import MenuCategory, MenuItem
from .models import Order, OrderItem


class OrderSnapshotTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="orders-tenant", name="Orders Tenant")
        self.host = "orders-tenant.localhost"
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Mains")
        self.item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Original Name", price="199.00")
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_order_creates_snapshot(self):
        resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 2, "modifier_ids": []}]},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["subtotal"], "398.00")
        self.assertEqual(body["items"][0]["item_name"], "Original Name")

    def test_later_menu_edit_does_not_mutate_historical_order(self):
        resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}]},
            content_type="application/json", HTTP_HOST=self.host)
        order_id = resp.json()["id"]

        # Simulate a later price/name edit via the admin/API - the item itself changes...
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        self.item.name = "Renamed Item"
        self.item.price = "999.00"
        self.item.save()
        reset_current_tenant(token)
        set_tenant_guc(None)

        # ...but the historical order's snapshot must be untouched.
        detail_resp = self.client.get(f"/api/orders/{order_id}/", HTTP_HOST=self.host)
        body = detail_resp.json()
        self.assertEqual(body["items"][0]["item_name"], "Original Name")
        self.assertEqual(body["items"][0]["unit_price"], "199.00")
        self.assertEqual(body["subtotal"], "199.00")

    def test_deleting_menu_item_does_not_delete_order_history(self):
        resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}]},
            content_type="application/json", HTTP_HOST=self.host)
        order_id = resp.json()["id"]

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        self.item.delete()
        reset_current_tenant(token)
        set_tenant_guc(None)

        detail_resp = self.client.get(f"/api/orders/{order_id}/", HTTP_HOST=self.host)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertEqual(detail_resp.json()["items"][0]["item_name"], "Original Name")