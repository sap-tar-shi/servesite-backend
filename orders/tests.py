from django.test import TestCase
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from menu.models import MenuCategory, MenuItem
from accounts.models import User, Membership
from .models import Order, OrderItem, OrderEvent
from tables.models import Table
from django.utils import timezone
from django.core.cache import cache


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
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 2, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_at_counter"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["subtotal"], "398.00")
        self.assertEqual(body["items"][0]["item_name"], "Original Name")

    def test_later_menu_edit_does_not_mutate_historical_order(self):
        resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
            "order_type": "takeaway", "payment_mode": "pay_at_counter"},
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
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
            "order_type": "takeaway", "payment_mode": "pay_at_counter"},
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


class OrderTypeResolutionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="ordertype-tenant", name="OrderType Tenant")
        self.host = "ordertype-tenant.localhost"
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Mains")
        self.item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Burger", price="199.00")
        self.table = Table.objects.create(tenant=self.tenant, label="Table 1")
        self.inactive_table = Table.objects.create(tenant=self.tenant, label="Table 2", is_active=False)
        reset_current_tenant(token)
        set_tenant_guc(None)

    def _place(self, extra):
        return self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
             "payment_mode": "pay_at_counter", **extra},
            content_type="application/json", HTTP_HOST=self.host)

    def test_valid_table_token_resolves_dine_in(self):
        resp = self._place({"table_token": self.table.table_token})
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["order_type"], "dine_in")
        self.assertEqual(body["table"], str(self.table.id))

    def test_client_cannot_override_order_type_when_token_present(self):
        resp = self._place({"table_token": self.table.table_token, "order_type": "online"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["order_type"], "dine_in")  # token wins regardless of client input

    def test_invalid_table_token_rejected(self):
        resp = self._place({"table_token": "not-a-real-token"})
        self.assertEqual(resp.status_code, 400)

    def test_inactive_table_token_rejected(self):
        resp = self._place({"table_token": self.inactive_table.table_token})
        self.assertEqual(resp.status_code, 400)

    def test_takeaway_without_token(self):
        resp = self._place({"order_type": "takeaway"})
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()["table"])

    def test_online_requires_address(self):
        resp = self._place({"order_type": "online"})
        self.assertEqual(resp.status_code, 400)

    def test_online_with_address_succeeds(self):
        resp = self._place({"order_type": "online", "address": "123 Main St"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["address"], "123 Main St")

    def test_no_token_and_no_order_type_rejected(self):
        resp = self._place({})
        self.assertEqual(resp.status_code, 400)


class OrderStateMachineTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="statemachine-tenant", name="State Machine Tenant")
        self.host = "statemachine-tenant.localhost"
        self.kitchen = User.objects.create_user(email="kitchen@sm.com", password="testpass123")
        Membership.objects.create(user=self.kitchen, tenant=self.tenant, role=Membership.ROLE_KITCHEN)

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Mains")
        self.item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Burger", price="199.00")
        reset_current_tenant(token)
        set_tenant_guc(None)

        self.client.post("/api/auth/login/", {"email": "kitchen@sm.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    def _place_order(self, order_type="takeaway"):
        resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
             "order_type": order_type, "payment_mode": "pay_at_counter"},
            content_type="application/json", HTTP_HOST=self.host)
        return resp.json()["id"]

    def test_creation_logs_placed_event(self):
        order_id = self._place_order()
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        events = OrderEvent.objects.filter(order_id=order_id)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().to_status, "placed")
        self.assertIsNone(events.first().actor)
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_valid_transition_succeeds_and_logs_actor(self):
        order_id = self._place_order()
        resp = self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": "accepted"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "accepted")

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        event = OrderEvent.objects.filter(order_id=order_id, to_status="accepted").first()
        self.assertEqual(event.actor.email, "kitchen@sm.com")
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_illegal_transition_rejected(self):
        order_id = self._place_order()
        resp = self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": "completed"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)

    def test_served_rejected_for_takeaway_order(self):
        order_id = self._place_order(order_type="takeaway")
        for step in ["accepted", "preparing", "ready"]:
            self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": step},
                content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": "served"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)

    def test_handed_over_accepted_for_takeaway_order(self):
        order_id = self._place_order(order_type="takeaway")
        for step in ["accepted", "preparing", "ready", "handed_over"]:
            resp = self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": step},
                content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "handed_over")

    def test_cancelled_is_terminal(self):
        order_id = self._place_order()
        self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": "cancelled"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": "accepted"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)


class PaymentModeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="paymode-tenant", name="PayMode Tenant", online_payment_enabled=False)
        self.connected_tenant = Tenant.objects.create(slug="paymode-connected", name="Connected", online_payment_enabled=True)
        self.host = "paymode-tenant.localhost"
        self.connected_host = "paymode-connected.localhost"

        for tenant in (self.tenant, self.connected_tenant):
            token = set_current_tenant(tenant)
            set_tenant_guc(tenant.id)
            category = MenuCategory.objects.create(tenant=tenant, name="Mains")
            MenuItem.objects.create(tenant=tenant, category=category, name="Burger", price="199.00")
            reset_current_tenant(token)
            set_tenant_guc(None)

    def _item_id(self, host):
        token = set_current_tenant(self.tenant if host == self.host else self.connected_tenant)
        set_tenant_guc((self.tenant if host == self.host else self.connected_tenant).id)
        item = MenuItem.objects.get(name="Burger")
        reset_current_tenant(token)
        set_tenant_guc(None)
        return str(item.id)

    def test_pay_at_counter_always_allowed(self):
        resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": self._item_id(self.host), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_at_counter"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 201)

    def test_pay_now_rejected_when_not_connected(self):
        resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": self._item_id(self.host), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_now"},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)

    def test_pay_now_allowed_when_connected(self):
        resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": self._item_id(self.connected_host), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_now"},
            content_type="application/json", HTTP_HOST=self.connected_host)
        self.assertEqual(resp.status_code, 201)

    def test_status_endpoint_reflects_connection(self):
        resp = self.client.get("/api/payments/status/", HTTP_HOST=self.host)
        self.assertFalse(resp.json()["online_payment_enabled"])
        resp = self.client.get("/api/payments/status/", HTTP_HOST=self.connected_host)
        self.assertTrue(resp.json()["online_payment_enabled"])


class LiveOrdersTests(TestCase):
    def setUp(self):
        cache.clear()  # avoid cross-test cache pollution given the 2s cache window
        self.tenant = Tenant.objects.create(slug="live-tenant", name="Live Tenant")
        self.host = "live-tenant.localhost"
        self.kitchen = User.objects.create_user(email="kitchen@live.com", password="testpass123")
        Membership.objects.create(user=self.kitchen, tenant=self.tenant, role=Membership.ROLE_KITCHEN)
        self.staff = User.objects.create_user(email="waiter@live.com", password="testpass123")
        Membership.objects.create(user=self.staff, tenant=self.tenant, role=Membership.ROLE_WAITER)

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Mains")
        self.item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Burger", price="199.00")
        reset_current_tenant(token)
        set_tenant_guc(None)

        self.client.post("/api/auth/login/", {"email": "kitchen@live.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    def test_returns_only_orders_changed_since_cursor(self):
        cutoff = timezone.now()
        self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_at_counter"},
            content_type="application/json", HTTP_HOST=self.host)

        resp = self.client.get("/api/orders/live/", {"since": cutoff.isoformat()}, HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_orders_before_cursor_excluded(self):
        self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_at_counter"},
            content_type="application/json", HTTP_HOST=self.host)

        cutoff_after = timezone.now()
        resp = self.client.get("/api/orders/live/", {"since": cutoff_after.isoformat()}, HTTP_HOST=self.host)
        self.assertEqual(resp.json(), [])

    def test_status_transition_updates_the_cursor(self):
        create_resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_at_counter"},
            content_type="application/json", HTTP_HOST=self.host)
        order_id = create_resp.json()["id"]

        cutoff = timezone.now()
        cache.clear()
        self.client.post(f"/api/orders/{order_id}/transition/", {"to_status": "accepted"},
            content_type="application/json", HTTP_HOST=self.host)

        resp = self.client.get("/api/orders/live/", {"since": cutoff.isoformat()}, HTTP_HOST=self.host)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["status"], "accepted")

    def test_waiter_role_can_also_access(self):
        self.client.logout()
        self.client.post("/api/auth/login/", {"email": "waiter@live.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.get("/api/orders/live/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)

    def test_invalid_since_param_rejected(self):
        resp = self.client.get("/api/orders/live/?since=not-a-date", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)