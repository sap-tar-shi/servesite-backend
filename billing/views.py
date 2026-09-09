from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from accounts.permissions import HasModulePermission
from .models import Plan, Subscription
from .serializers import PlanSerializer, SubscriptionSerializer
from .razorpay_client import create_subscription
from django.conf import settings


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