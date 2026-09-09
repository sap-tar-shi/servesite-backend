import json
import hmac
import hashlib
import uuid
from django.test import TestCase, Client
from django.conf import settings
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from billing.models import Plan, Subscription


class BillingWebhookTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="webhook-test-tenant", name="Webhook Test")
        self.plan = Plan.objects.create(name="TestPlan", price="100.00", razorpay_plan_id="plan_test123")
        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        try:
            self.sub = Subscription.objects.create(
                tenant=self.tenant, plan=self.plan,
                razorpay_subscription_id="sub_test123", status="created",
            )
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)

    def _signed_post(self, payload):
        body = json.dumps(payload).encode()
        sig = hmac.new(settings.PLATFORM_RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        return Client().post(
            "/api/billing/webhook/", data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )

    def test_subscription_activated_updates_status(self):
        payload = {
            "id": "evt_1",
            "event": "subscription.activated",
            "payload": {"subscription": {"entity": {
                "id": "sub_test123",
                "notes": {"tenant_id": str(self.tenant.id)},
                "current_end": 1893456000,
            }}},
        }
        resp = self._signed_post(payload)
        self.assertEqual(resp.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, "active")

    def test_duplicate_event_is_noop(self):
        payload = {
            "id": "evt_dup",
            "event": "subscription.halted",
            "payload": {"subscription": {"entity": {
                "id": "sub_test123",
                "notes": {"tenant_id": str(self.tenant.id)},
            }}},
        }
        self._signed_post(payload)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, "halted")
        # second identical delivery should not error and should not re-apply
        resp2 = self._signed_post(payload)
        self.assertEqual(resp2.status_code, 200)

    def test_bad_signature_rejected(self):
        resp = Client().post(
            "/api/billing/webhook/",
            data=json.dumps({"event": "subscription.activated"}), content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="wrong",
        )
        self.assertEqual(resp.status_code, 400)