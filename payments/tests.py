from unittest.mock import patch, Mock
from django.test import TestCase
from django.utils import timezone
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from accounts.models import User, Membership
from .models import RazorpayConnection, RazorpayConnectAttempt


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