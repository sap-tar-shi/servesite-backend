from django.urls import path
from .views import OrderCreateView, OrderDetailView, OrderTransitionView, LiveOrdersView

urlpatterns = [
    path("", OrderCreateView.as_view(), name="order-create"),
    path("<uuid:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("<uuid:pk>/transition/", OrderTransitionView.as_view(), name="order-transition"),
    path("live/", LiveOrdersView.as_view(), name="orders-live"),
]