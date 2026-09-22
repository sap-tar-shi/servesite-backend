from django.urls import path
from .views import DomainView, DomainVerifyView, PublicDomainResolveView

urlpatterns = [
    path("", DomainView.as_view(), name="domain-detail"),
    path("verify/", DomainVerifyView.as_view(), name="domain-verify"),
    path("resolve/", PublicDomainResolveView.as_view(), name="domain-resolve"),
]