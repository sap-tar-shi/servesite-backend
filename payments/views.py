import secrets
import requests
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from accounts.permissions import HasModulePermission
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from .models import RazorpayConnection, RazorpayConnectAttempt


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