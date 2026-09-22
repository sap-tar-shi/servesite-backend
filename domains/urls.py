from django.urls import path
from .views import DomainView, DomainVerifyView

urlpatterns = [
    path("", DomainView.as_view(), name="domain-detail"),
    path("verify/", DomainVerifyView.as_view(), name="domain-verify"),
]