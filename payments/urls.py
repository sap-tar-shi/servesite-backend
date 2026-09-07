from django.urls import path
from .views import RazorpayConnectStartView, RazorpayConnectCallbackView, PaymentStatusView, PaymentCreateView

urlpatterns = [
    path("razorpay/connect/", RazorpayConnectStartView.as_view(), name="razorpay-connect-start"),
    path("status/", PaymentStatusView.as_view(), name="payment-status"),    
    path("create/", PaymentCreateView.as_view(), name="payment-create"),
]

# Registered separately in config/urls.py at a fixed, non-tenant path -
# see step 6.