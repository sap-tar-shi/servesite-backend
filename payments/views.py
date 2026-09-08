import secrets
import json
import hmac
import hashlib
import requests
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status, generics
from accounts.permissions import HasModulePermission
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from orders.models import Order
from orders.serializers import OrderSerializer
from .models import RazorpayConnection, RazorpayConnectAttempt, Payment, WebhookEvent


class RazorpayConnectStartView(APIView):
    """
    GET /api/payments/razorpay/connect/  - owner only (billing_staff_domains
    per §12). Returns the URL the admin frontend should redirect the
    owner's browser to.
    """

    permission_classes = [HasModulePermission("billing_staff_domains")]

    def get(self, request):
        state = secrets.token_urlsafe(32)
        RazorpayConnectAttempt.objects.create(tenant=request.tenant, state=state)

        params = {
            "response_type": "code",
            "client_id": settings.RAZORPAY_CLIENT_ID,
            "redirect_uri": settings.RAZORPAY_REDIRECT_URI,
            "scope": "read_write",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return Response({"authorize_url": f"https://auth.razorpay.com/authorize?{query}"})


class RazorpayConnectCallbackView(APIView):
    """
    GET /api/payments/razorpay/callback/  - fixed platform-level URL,
    whitelisted with Razorpay; NOT under any tenant subdomain, since
    redirect_uri can't vary per tenant. Tenant is resolved via `state`,
    not via Host header (there is no meaningful Host here).
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            return Response({"detail": "Missing code or state."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            attempt = RazorpayConnectAttempt.unscoped.get(state=state, consumed=False)
        except RazorpayConnectAttempt.DoesNotExist:
            return Response({"detail": "Invalid or already-used state."}, status=status.HTTP_400_BAD_REQUEST)

        token_resp = requests.post(
            "https://auth.razorpay.com/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.RAZORPAY_CLIENT_ID,
                "client_secret": settings.RAZORPAY_CLIENT_SECRET,
                "redirect_uri": settings.RAZORPAY_REDIRECT_URI,
            },
            timeout=10,
        )
        if not token_resp.ok:
            return Response({"detail": "Razorpay token exchange failed."}, status=status.HTTP_400_BAD_REQUEST)

        data = token_resp.json()
        tenant = attempt.tenant

        token = set_current_tenant(tenant)
        set_tenant_guc(tenant.id)
        try:
            connection, _ = RazorpayConnection.objects.get_or_create(tenant=tenant, defaults={
                "access_token_encrypted": b"", "refresh_token_encrypted": b"", "token_expires_at": timezone.now(),
            })
            connection.set_tokens(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=timezone.now() + timedelta(seconds=data.get("expires_in", 3600)),
            )
            tenant.online_payment_enabled = True
            tenant.save(update_fields=["online_payment_enabled"])
            attempt.consumed = True
            attempt.save(update_fields=["consumed"])
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)

        return HttpResponseRedirect(f"http://{tenant.slug}.localhost:3000/manage/billing?razorpay=connected")


class PaymentStatusView(APIView):
    """
    GET /api/payments/status/  - no auth (diner-facing checkout page needs
    this to decide whether to render the "Pay now" option at all).
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"online_payment_enabled": request.tenant.online_payment_enabled})


class PaymentCreateView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        order_id = request.data.get("order_id")
        try:
            order = Order.objects.get(id=order_id, payment_mode="pay_now")
        except Order.DoesNotExist:
            return Response({"detail": "Order not found or not a pay-now order."}, status=status.HTTP_400_BAD_REQUEST)

        if hasattr(order, "payment"):
            existing = order.payment
            connection = RazorpayConnection.objects.filter(tenant=request.tenant, is_active=True).first()
            return Response({
                "razorpay_order_id": existing.razorpay_order_id,
                "razorpay_key_id": connection.get_access_token() if connection and connection.auth_mode == "direct_keys" else None,
                "amount": str(existing.amount),
                "currency": "INR",  # Payment model doesn't store currency separately - always INR at creation time (see the create-branch below)
            })

        connection = RazorpayConnection.objects.filter(tenant=request.tenant, is_active=True).first()
        if not connection:
            return Response({"detail": "Online payment not available for this restaurant."}, status=status.HTTP_400_BAD_REQUEST)

        resp = requests.post(
            "https://api.razorpay.com/v1/orders",
            json={"amount": int(order.subtotal * 100), "currency": "INR", "receipt": str(order.id)},
            headers=connection.get_auth_header(),
            timeout=10,
        )
        if not resp.ok:
            return Response({"detail": "Could not create Razorpay order."}, status=status.HTTP_502_BAD_GATEWAY)

        data = resp.json()
        payment = Payment.objects.create(
            tenant=request.tenant, order=order, razorpay_order_id=data["id"], amount=order.subtotal,
        )
        return Response({
            "razorpay_order_id": payment.razorpay_order_id,
            "razorpay_key_id": connection.get_access_token() if connection.auth_mode == "direct_keys" else None,
            "amount": data["amount"],
            "currency": data.get("currency", "INR"),
        })


class PaymentWebhookView(APIView):
    """
    NOT YET VERIFIED against a real Razorpay-delivered payload - see
    docs/deferred-to-prod.md. Razorpay's dashboard refuses localhost
    webhook URLs outright, and ngrok isn't available in this dev
    environment, so this is currently only proven against synthetic
    signed payloads in payments/tests.py, not a live delivery.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, TypeError):
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)

        event_type = payload.get("event", "")
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        razorpay_order_id = entity.get("order_id")
        if not razorpay_order_id:
            return Response({"detail": "Missing order_id in payload."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.unscoped.select_related("tenant", "order").get(razorpay_order_id=razorpay_order_id)
        except Payment.DoesNotExist:
            return Response({"detail": "Unknown razorpay_order_id."}, status=status.HTTP_400_BAD_REQUEST)

        tenant = payment.tenant
        connection = RazorpayConnection.unscoped.get(tenant=tenant)

        signature = request.headers.get("X-Razorpay-Signature", "")
        expected = hmac.new(connection.webhook_secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

        event_id = payload.get("id") or f"{razorpay_order_id}:{event_type}"

        token = set_current_tenant(tenant)
        set_tenant_guc(tenant.id)
        try:
            if WebhookEvent.objects.filter(event_id=event_id).exists():
                return Response({"detail": "Already processed."}, status=status.HTTP_200_OK)
            WebhookEvent.objects.create(tenant=tenant, event_id=event_id, event_type=event_type)

            if event_type == "payment.captured" and payment.status != "captured":
                payment.status = "captured"
                payment.razorpay_payment_id = entity.get("id", "")
                payment.save(update_fields=["status", "razorpay_payment_id"])
                if payment.order.status == "placed":
                    payment.order.transition_to("paid", actor=None)
            elif event_type == "payment.failed":
                payment.status = "failed"
                payment.save(update_fields=["status"])
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)


class RefundView(APIView):
    """
    POST /api/payments/refund/<order_id>/  - owner/manager only. Issues
    the refund on the RESTAURANT's own Razorpay account (never the
    platform's), per §9's "platform never holds/splits funds" guardrail -
    same auth_header mechanism as PaymentCreateView.
    """

    permission_classes = [HasModulePermission("billing_staff_domains")]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Order not found."}, status=status.HTTP_400_BAD_REQUEST)

        if not hasattr(order, "payment") or order.payment.status != "captured":
            return Response({"detail": "Order has no captured payment to refund."}, status=status.HTTP_400_BAD_REQUEST)

        connection = RazorpayConnection.objects.filter(tenant=request.tenant, is_active=True).first()
        if not connection:
            return Response({"detail": "Payment connection not found."}, status=status.HTTP_400_BAD_REQUEST)

        resp = requests.post(
            f"https://api.razorpay.com/v1/payments/{order.payment.razorpay_payment_id}/refund",
            json={},  # full refund; partial refunds (amount=...) are a future extension, not needed by this AC
            headers=connection.get_auth_header(),
            timeout=10,
        )
        if not resp.ok:
            return Response({"detail": "Refund request failed at Razorpay."}, status=status.HTTP_502_BAD_GATEWAY)

        order.payment.status = "failed"  # reusing existing choices; consider adding a dedicated "refunded" Payment status later if this matters for reporting
        order.payment.save(update_fields=["status"])
        try:
            order.transition_to("refunded", actor=request.user)
        except ValueError as e:
            return Response({"detail": f"Refund issued at Razorpay, but order state update failed: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(OrderSerializer(order).data)