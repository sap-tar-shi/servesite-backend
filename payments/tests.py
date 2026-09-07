import hmac
import hashlib
import json
from datetime import timedelta
from unittest.mock import patch, Mock
from django.test import TestCase
from django.utils import timezone
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from accounts.models import User, Membership
from menu.models import MenuCategory, MenuItem
from orders.models import Order
from .models import RazorpayConnection, RazorpayConnectAttempt, Payment, WebhookEvent


class RazorpayConnectTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="payments-tenant", name="Payments Tenant")
        self.host = "payments-tenant.localhost"
        self.owner = User.objects.create_user(email="owner@payments.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)
        self.client.post("/api/auth/login/", {"email": "owner@payments.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    def test_connect_start_returns_authorize_url_and_records_attempt(self):
        resp = self.client.get("/api/payments/razorpay/connect/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("https://auth.razorpay.com/authorize", resp.json()["authorize_url"])

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        self.assertEqual(RazorpayConnectAttempt.objects.count(), 1)
        reset_current_tenant(token)
        set_tenant_guc(None)

    @patch("payments.views.requests.post")
    def test_callback_exchanges_code_and_flips_tenant_flag(self, mock_post):
        mock_post.return_value = Mock(ok=True, json=lambda: {
            "access_token": "fake-access", "refresh_token": "fake-refresh", "expires_in": 3600,
        })

        start_resp = self.client.get("/api/payments/razorpay/connect/", HTTP_HOST=self.host)
        # Extract state from the attempt row directly (real flow: Razorpay echoes it back)
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        attempt = RazorpayConnectAttempt.objects.first()
        state = attempt.state
        reset_current_tenant(token)
        set_tenant_guc(None)

        callback_resp = self.client.get(f"/api/payments/razorpay/callback/?code=fake-code&state={state}")
        self.assertEqual(callback_resp.status_code, 302)  # redirect back to /manage/billing

        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.online_payment_enabled)

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        connection = RazorpayConnection.objects.first()
        self.assertEqual(connection.get_access_token(), "fake-access")
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_callback_rejects_unknown_state(self):
        resp = self.client.get("/api/payments/razorpay/callback/?code=x&state=not-a-real-state")
        self.assertEqual(resp.status_code, 400)

    def test_staff_cannot_start_connect(self):
        staff = User.objects.create_user(email="staff@payments.com", password="testpass123")
        Membership.objects.create(user=staff, tenant=self.tenant, role=Membership.ROLE_STAFF)
        self.client.logout()
        self.client.post("/api/auth/login/", {"email": "staff@payments.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.get("/api/payments/razorpay/connect/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 403)


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="pay-tenant", name="Pay Tenant", online_payment_enabled=True)
        self.host = "pay-tenant.localhost"
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Mains")
        self.item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Burger", price="199.00")
        self.connection = RazorpayConnection.objects.create(
            tenant=self.tenant, access_token_encrypted=b"", refresh_token_encrypted=b"",
            token_expires_at=timezone.now(), auth_mode="direct_keys", webhook_secret="testsecret",
        )
        self.connection.set_tokens("rzp_test_fakekey", "fakesecret", timezone.now() + timedelta(days=1))
        reset_current_tenant(token)
        set_tenant_guc(None)

        order_resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_now"},
            content_type="application/json", HTTP_HOST=self.host)
        self.order_id = order_resp.json()["id"]

    @patch("payments.views.requests.post")
    def test_payment_create_calls_razorpay_and_stores_payment(self, mock_post):
        mock_post.return_value = Mock(ok=True, json=lambda: {"id": "order_fake123", "currency": "INR", "amount": 19900})
        resp = self.client.post("/api/payments/create/", {"order_id": self.order_id},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["razorpay_order_id"], "order_fake123")

    @patch("payments.views.requests.post")
    def test_payment_create_is_idempotent(self, mock_post):
        mock_post.return_value = Mock(ok=True, json=lambda: {"id": "order_fake123", "currency": "INR", "amount": 19900})
        self.client.post("/api/payments/create/", {"order_id": self.order_id},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.post("/api/payments/create/", {"order_id": self.order_id},
            content_type="application/json", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_post.call_count, 1)

    def _send_webhook(self, event_type, razorpay_order_id, payment_id="pay_fake456"):
        body = json.dumps({
            "event": event_type,
            "payload": {"payment": {"entity": {"order_id": razorpay_order_id, "id": payment_id}}},
        }).encode()
        signature = hmac.new(b"testsecret", body, hashlib.sha256).hexdigest()
        return self.client.post(
            "/api/payments/webhook/", data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

    @patch("payments.views.requests.post")
    def test_webhook_captures_payment_and_transitions_order(self, mock_post):
        mock_post.return_value = Mock(ok=True, json=lambda: {"id": "order_fake123", "currency": "INR", "amount": 19900})
        self.client.post("/api/payments/create/", {"order_id": self.order_id},
            content_type="application/json", HTTP_HOST=self.host)

        resp = self._send_webhook("payment.captured", "order_fake123")
        self.assertEqual(resp.status_code, 200)

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        payment = Payment.objects.get(razorpay_order_id="order_fake123")
        self.assertEqual(payment.status, "captured")
        order = Order.objects.get(id=self.order_id)
        self.assertEqual(order.status, "paid")
        reset_current_tenant(token)
        set_tenant_guc(None)

    @patch("payments.views.requests.post")
    def test_duplicate_webhook_is_noop(self, mock_post):
        mock_post.return_value = Mock(ok=True, json=lambda: {"id": "order_fake123", "currency": "INR", "amount": 19900})
        self.client.post("/api/payments/create/", {"order_id": self.order_id},
            content_type="application/json", HTTP_HOST=self.host)
        self._send_webhook("payment.captured", "order_fake123")
        self._send_webhook("payment.captured", "order_fake123")

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_webhook_rejects_bad_signature(self):
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"order_id": "order_fake123", "id": "x"}}}}).encode()
        resp = self.client.post("/api/payments/webhook/", data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="wrong-signature")
        self.assertEqual(resp.status_code, 400)


class RefundTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="refund-tenant", name="Refund Tenant", online_payment_enabled=True)
        self.host = "refund-tenant.localhost"
        self.owner = User.objects.create_user(email="owner@refund.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Mains")
        self.item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Burger", price="199.00")
        self.connection = RazorpayConnection.objects.create(
            tenant=self.tenant, access_token_encrypted=b"", refresh_token_encrypted=b"",
            token_expires_at=timezone.now(), auth_mode="direct_keys", webhook_secret="testsecret",
        )
        self.connection.set_tokens("rzp_test_fakekey", "fakesecret", timezone.now() + timedelta(days=1))
        reset_current_tenant(token)
        set_tenant_guc(None)

        self.client.post("/api/auth/login/", {"email": "owner@refund.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)

    @patch("payments.views.requests.post")
    def test_refund_requires_captured_payment(self, mock_post):
        order_resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_at_counter"},
            content_type="application/json", HTTP_HOST=self.host)
        order_id = order_resp.json()["id"]

        resp = self.client.post(f"/api/payments/refund/{order_id}/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)
        mock_post.assert_not_called()

    @patch("payments.views.requests.post")
    def test_successful_refund_transitions_order(self, mock_post):
        def side_effect(url, **kwargs):
            if "orders" in url:
                return Mock(ok=True, json=lambda: {"id": "order_fake123", "currency": "INR", "amount": 19900})
            return Mock(ok=True, json=lambda: {"id": "rfnd_fake789"})
        mock_post.side_effect = side_effect

        order_resp = self.client.post("/api/orders/",
            {"items": [{"menu_item_id": str(self.item.id), "quantity": 1, "modifier_ids": []}],
             "order_type": "takeaway", "payment_mode": "pay_now"},
            content_type="application/json", HTTP_HOST=self.host)
        order_id = order_resp.json()["id"]
        self.client.post("/api/payments/create/", {"order_id": order_id},
            content_type="application/json", HTTP_HOST=self.host)

        body = json.dumps({"event": "payment.captured",
            "payload": {"payment": {"entity": {"order_id": "order_fake123", "id": "pay_fake456"}}}}).encode()
        signature = hmac.new(b"testsecret", body, hashlib.sha256).hexdigest()
        self.client.post("/api/payments/webhook/", data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature)

        resp = self.client.post(f"/api/payments/refund/{order_id}/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "refunded")

    def test_staff_cannot_issue_refund(self):
        staff = User.objects.create_user(email="staff@refund.com", password="testpass123")
        Membership.objects.create(user=staff, tenant=self.tenant, role=Membership.ROLE_STAFF)
        self.client.logout()
        self.client.post("/api/auth/login/", {"email": "staff@refund.com", "password": "testpass123"},
            content_type="application/json", HTTP_HOST=self.host)
        resp = self.client.post("/api/payments/refund/00000000-0000-0000-0000-000000000000/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 403)