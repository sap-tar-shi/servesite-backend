from django.urls import path
from .views import (
    LoginView, LogoutView, MeView, PricingView,
    SiteCustomizationView, LiveOrdersView, BillingView,
    StaffCredentialsView, InviteStaffView, StaffModeView,
    SignupView, VerifyEmailView, SlugSuggestionsView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("slug-suggestions/", SlugSuggestionsView.as_view(), name="slug-suggestions"),
    path("pricing/", PricingView.as_view(), name="pricing"),
    path("site-customization/", SiteCustomizationView.as_view(), name="site-customization"),
    path("live-orders/", LiveOrdersView.as_view(), name="live-orders"),
    path("billing/", BillingView.as_view(), name="billing"),
    path("staff-credentials/", StaffCredentialsView.as_view(), name="staff-credentials"),
    path("staff/", InviteStaffView.as_view(), name="staff-invite"),
    path("staff-mode/", StaffModeView.as_view(), name="staff-mode"),
]