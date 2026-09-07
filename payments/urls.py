from django.urls import path
from .views import RazorpayConnectStartView, RazorpayConnectCallbackView

urlpatterns = [
    path("razorpay/connect/", RazorpayConnectStartView.as_view(), name="razorpay-connect-start"),
]

# Registered separately in config/urls.py at a fixed, non-tenant path -
# see step 6.