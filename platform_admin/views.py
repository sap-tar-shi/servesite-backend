from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import SuperAdmin
from .permissions import IsPlatformAdminOrigin, IsSuperAdminAuthenticated


class SuperAdminLoginView(APIView):
    """Origin/IP-gated but not auth-gated (this IS the auth step)."""

    permission_classes = [IsPlatformAdminOrigin]

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")
        admin = SuperAdmin.objects.filter(email=email, is_active=True).first()
        if admin is None or not admin.check_password(password):
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        request.session["superadmin_id"] = str(admin.id)
        request.session.cycle_key()  # rotate session id on privilege elevation
        return Response({"email": admin.email})


class SuperAdminLogoutView(APIView):
    permission_classes = [IsSuperAdminAuthenticated]

    def post(self, request):
        request.session.pop("superadmin_id", None)
        return Response({"detail": "Logged out."})


class SuperAdminMeView(APIView):
    permission_classes = [IsSuperAdminAuthenticated]

    def get(self, request):
        return Response({"email": request.superadmin.email})