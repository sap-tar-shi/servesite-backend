from django.urls import path
from .views import PlanListView, SubscriptionView

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="plan-list"),
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
]