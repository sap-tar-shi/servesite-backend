from django.contrib import admin
from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "billing_interval", "is_active", "razorpay_plan_id", "created_at")
    list_filter = ("billing_interval", "is_active")
    search_fields = ("name",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "plan", "status", "current_period_end", "updated_at")
    list_filter = ("status",)
    search_fields = ("tenant__slug",)

    def get_queryset(self, request):
        # Admin needs cross-tenant visibility — explicit unscoped read, logged.
        return Subscription.unscoped.all()