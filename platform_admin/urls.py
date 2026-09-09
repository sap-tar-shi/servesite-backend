from django.urls import path
from .views import SuperAdminLoginView, SuperAdminLogoutView, SuperAdminMeView

urlpatterns = [
    path("login/", SuperAdminLoginView.as_view(), name="superadmin-login"),
    path("logout/", SuperAdminLogoutView.as_view(), name="superadmin-logout"),
    path("me/", SuperAdminMeView.as_view(), name="superadmin-me"),
]