from django.urls import path
from .views import LoginView, LogoutView, MeView, PricingView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("pricing/", PricingView.as_view(), name="pricing"),
]