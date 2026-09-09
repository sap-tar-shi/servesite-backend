from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from accounts.permissions import HasModulePermission
from .models import Plan, Subscription
from .serializers import PlanSerializer, SubscriptionSerializer
from .razorpay_client import create_subscription
import json
import hmac
import hashlib
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from .models import BillingWebhookEvent


class PlanListView(APIView):
    """Public-ish list of active plans an owner can pick from. Any authenticated
    tenant member can view (not gated to owner) since it's just pricing info."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True)
        return Response(PlanSerializer(plans, many=True).data)


class SubscriptionView(APIView):
    """
    GET: current tenant's Subscription (or null if none yet).
    POST: owner picks a plan_id -> creates a Razorpay Subscription awaiting
    authentication payment, and the local Subscription row (status="created").
    Gated owner-only, reusing the existing billing_staff_domains module.
    """

    permission_classes = [HasModulePermission("billing_staff_domains")]

    def get(self, request):
        sub = Subscription.objects.select_related("plan").filter(tenant=request.tenant).first()
        if not sub:
            return Response(None)
        return Response(SubscriptionSerializer(sub).data)

    def post(self, request):
        if Subscription.objects.filter(tenant=request.tenant).exists():
            return Response({"detail": "Tenant already has a subscription. Use the change-plan flow instead."}, status=status.HTTP_400_BAD_REQUEST)

        plan_id = request.data.get("plan_id")
        try:
            plan = Plan.objects.get(id=plan_id, is_active=True)
        except Plan.DoesNotExist:
            return Response({"detail": "Invalid plan."}, status=status.HTTP_400_BAD_REQUEST)

        if not plan.razorpay_plan_id:
            return Response({"detail": "Plan not yet synced to Razorpay."}, status=status.HTTP_502_BAD_GATEWAY)

        data = create_subscription(
            razorpay_plan_id=plan.razorpay_plan_id,
            total_count=12,  # 12 billing cycles, then renews via a fresh Subscription - revisit if auto-renewing subs are needed later
            notes={"tenant_slug": request.tenant.slug, "tenant_id": str(request.tenant.id)},
        )

        sub = Subscription.objects.create(
            tenant=request.tenant,
            plan=plan,
            razorpay_subscription_id=data["id"],
            status="created",
        )
        return Response({
            "subscription": SubscriptionSerializer(sub).data,
            "razorpay_subscription_id": data["id"],
            "razorpay_key_id": settings.PLATFORM_RAZORPAY_KEY_ID,
        }, status=status.HTTP_201_CREATED)


class BillingWebhookView(APIView):
    """
    Platform-account webhook (Subscriptions events) - NOT YET VERIFIED against
    a live delivery, same limitation as payments.PaymentWebhookView (see
    docs/deferred-to-prod.md): Razorpay refuses localhost webhook URLs and
    ngrok isn't available here. Proven only against synthetic signed
    payloads in billing/tests.py until this goes to production.

    Unlike PaymentWebhookView, this is platform-level, not per-tenant - one
    fixed PLATFORM_RAZORPAY_WEBHOOK_SECRET, not a RazorpayConnection lookup.
    Tenant is identified via notes.tenant_id set at Subscription creation.
    """

    permission_classes = [permissions.AllowAny]

    ACTIVE_STATES = {"authenticated", "activated", "charged"}
    STATUS_MAP = {
        "subscription.authenticated": "active",
        "subscription.activated": "active",
        "subscription.charged": "active",
        "subscription.pending": "pending",
        "subscription.halted": "halted",
        "subscription.cancelled": "cancelled",
        "subscription.paused": "paused",
        "subscription.completed": "completed",
    }

    def post(self, request):
        signature = request.headers.get("X-Razorpay-Signature", "")
        expected = hmac.new(
            settings.PLATFORM_RAZORPAY_WEBHOOK_SECRET.encode(), request.body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, TypeError):
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)

        event_type = payload.get("event", "")
        new_status = self.STATUS_MAP.get(event_type)
        if new_status is None:
            return Response({"detail": "Ignored event type."}, status=status.HTTP_200_OK)

        sub_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        razorpay_subscription_id = sub_entity.get("id")
        notes = sub_entity.get("notes", {})
        tenant_id = notes.get("tenant_id")
        if not razorpay_subscription_id or not tenant_id:
            return Response({"detail": "Missing subscription id or tenant_id in notes."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({"detail": "Unknown tenant."}, status=status.HTTP_400_BAD_REQUEST)

        event_id = payload.get("id") or f"{razorpay_subscription_id}:{event_type}"

        token = set_current_tenant(tenant)
        set_tenant_guc(tenant.id)
        try:
            if BillingWebhookEvent.objects.filter(event_id=event_id).exists():
                return Response({"detail": "Already processed."}, status=status.HTTP_200_OK)
            BillingWebhookEvent.objects.create(tenant=tenant, event_id=event_id, event_type=event_type)

            try:
                sub = Subscription.objects.get(tenant=tenant, razorpay_subscription_id=razorpay_subscription_id)
            except Subscription.DoesNotExist:
                return Response({"detail": "Unknown subscription."}, status=status.HTTP_400_BAD_REQUEST)

            previous_status = sub.status
            sub.status = new_status
            current_end = sub_entity.get("current_end")
            if current_end:
                from datetime import datetime, timezone as dt_timezone
                sub.current_period_end = datetime.fromtimestamp(current_end, tz=dt_timezone.utc)

            if new_status == "halted" and previous_status != "halted":
                sub.halted_at = timezone.now()
            elif new_status == "active":
                sub.halted_at = None
                # billing recovered - lift a billing-caused suspension automatically
                if tenant.status == Tenant.STATUS_SUSPENDED:
                    tenant.status = Tenant.STATUS_ACTIVE
                    tenant.save(update_fields=["status"])

            sub.save(update_fields=["status", "current_period_end", "halted_at", "updated_at"])
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)