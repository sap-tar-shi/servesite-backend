from django.urls import path
from .views import PlanListView, SubscriptionView, BillingWebhookView

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="plan-list"),
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
    path("webhook/", BillingWebhookView.as_view(), name="billing-webhook"),
]