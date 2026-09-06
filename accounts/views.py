from django.contrib.auth import authenticate, login, logout
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import LoginSerializer
from .models import Membership
from .permissions import HasModulePermission


def _serialize_user_with_memberships(user):
    memberships = Membership.objects.filter(user=user).select_related("tenant")
    return {
        "email": user.email,
        "id": str(user.id),
        "memberships": [
            {"tenant_slug": m.tenant.slug, "tenant_name": m.tenant.name, "role": m.role}
            for m in memberships
        ],
    }


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return Response(_serialize_user_with_memberships(user))


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [permissions.AllowAny]  # we do our own auth check below to control the status code

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "Not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(_serialize_user_with_memberships(request.user))


class PricingView(APIView):
    """
    Throwaway endpoint existing solely to prove RBAC enforcement per
    Implementation Plan P1-T11 AC. Real menu-pricing endpoints arrive in
    P1-T19 and will use this exact permission pattern.
    """

    permission_classes = [HasModulePermission("menu_management")]

    def get(self, request):
        return Response({"prices": ["confidential-pricing-data"]})