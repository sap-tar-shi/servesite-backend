from django.urls import path
from .views import OrderCreateView, OrderDetailView, OrderTransitionView

urlpatterns = [
    path("", OrderCreateView.as_view(), name="order-create"),
    path("<uuid:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("<uuid:pk>/transition/", OrderTransitionView.as_view(), name="order-transition"),
]