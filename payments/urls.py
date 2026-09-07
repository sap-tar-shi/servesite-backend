from django.urls import path
from .views import RazorpayConnectStartView, RazorpayConnectCallbackView
from .views import RazorpayConnectStartView, RazorpayConnectCallbackView, PaymentStatusView

urlpatterns = [
    path("razorpay/connect/", RazorpayConnectStartView.as_view(), name="razorpay-connect-start"),
    path("status/", PaymentStatusView.as_view(), name="payment-status"),    
]

# Registered separately in config/urls.py at a fixed, non-tenant path -
# see step 6.