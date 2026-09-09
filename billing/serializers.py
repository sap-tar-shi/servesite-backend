from rest_framework import serializers
from .models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "price", "billing_interval", "feature_limits"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = ["id", "plan", "status", "current_period_end", "razorpay_subscription_id"]


class PlanAdminSerializer(serializers.ModelSerializer):
    """Full read/write shape for super-admin plan management - unlike the
    tenant-facing PlanSerializer, this exposes razorpay_plan_id and is_active."""

    class Meta:
        model = Plan
        fields = ["id", "name", "price", "billing_interval", "feature_limits", "is_active", "razorpay_plan_id"]
        read_only_fields = ["razorpay_plan_id"]  # only sync_razorpay_plans sets this


class SubscriptionOversightSerializer(serializers.ModelSerializer):
    tenant_slug = serializers.CharField(source="tenant.slug", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id", "tenant_slug", "tenant_name", "plan_name", "status",
            "current_period_end", "mandate_status", "halted_at", "updated_at",
        ]