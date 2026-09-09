from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from tenants.models import Tenant
from accounts.models import User, Membership
from .serializers import TenantAdminSerializer, AuditLogSerializer
from .models import SuperAdmin, AuditLog
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


def _log(request, action, tenant=None, details=None):
    AuditLog.objects.create(
        superadmin=request.superadmin, action=action,
        target_tenant_id=tenant.id if tenant else None, details=details or {},
    )


class TenantListCreateView(APIView):
    """
    GET: list all tenants (cross-tenant read - deliberately uses Tenant's
    plain manager since Tenant itself isn't a TenantScopedModel; it's the
    thing being scoped against).
    POST: provision a new tenant + its owner Membership, audited.
    """

    permission_classes = [IsSuperAdminAuthenticated]

    def get(self, request):
        tenants = Tenant.objects.all().order_by("-created_at")
        return Response(TenantAdminSerializer(tenants, many=True).data)

    def post(self, request):
        slug = request.data.get("slug", "").strip().lower()
        name = request.data.get("name", "").strip()
        owner_email = request.data.get("owner_email", "").strip().lower()
        if not (slug and name and owner_email):
            return Response({"detail": "slug, name, and owner_email are all required."}, status=status.HTTP_400_BAD_REQUEST)

        if Tenant.objects.filter(slug=slug).exists():
            return Response({"detail": "That slug is already taken."}, status=status.HTTP_400_BAD_REQUEST)

        tenant = Tenant.objects.create(slug=slug, name=name, status=Tenant.STATUS_TRIAL)
        # shared staff account is auto-provisioned by accounts/signals.py's
        # post_save receiver - nothing to do here for that part.

        owner_user, owner_created = User.objects.get_or_create(email=owner_email)
        temp_password = None
        if owner_created:
            import secrets
            temp_password = secrets.token_urlsafe(12)
            owner_user.set_password(temp_password)
            owner_user.save()
        Membership.objects.get_or_create(user=owner_user, tenant=tenant, defaults={"role": Membership.ROLE_OWNER})

        _log(request, "tenant.create", tenant=tenant, details={"owner_email": owner_email, "owner_created": owner_created})

        return Response({
            "tenant": TenantAdminSerializer(tenant).data,
            "owner_email": owner_email,
            "owner_temp_password": temp_password,  # None if owner_email already existed - they use their existing password
        }, status=status.HTTP_201_CREATED)


class TenantDetailView(APIView):
    """GET: inspect a single tenant (cross-tenant, audited as a read)."""

    permission_classes = [IsSuperAdminAuthenticated]

    def get(self, request, tenant_id):
        tenant = get_object_or_404(Tenant, id=tenant_id)
        _log(request, "tenant.inspect", tenant=tenant)
        memberships = Membership.objects.filter(tenant=tenant).select_related("user")
        return Response({
            "tenant": TenantAdminSerializer(tenant).data,
            "memberships": [
                {"email": m.user.email, "role": m.role, "is_shared_account": m.is_shared_account}
                for m in memberships
            ],
        })


class TenantSuspendView(APIView):
    """POST: suspend or reactivate a tenant. Distinct from the automatic
    billing-driven suspension in billing/tasks.py - this is a manual
    operator action, audited with a reason."""

    permission_classes = [IsSuperAdminAuthenticated]

    def post(self, request, tenant_id):
        tenant = get_object_or_404(Tenant, id=tenant_id)
        new_status = request.data.get("status")
        reason = request.data.get("reason", "")
        if new_status not in (Tenant.STATUS_ACTIVE, Tenant.STATUS_SUSPENDED):
            return Response({"detail": "status must be 'active' or 'suspended'."}, status=status.HTTP_400_BAD_REQUEST)

        tenant.status = new_status
        tenant.save(update_fields=["status"])
        _log(request, f"tenant.{new_status}", tenant=tenant, details={"reason": reason})

        return Response(TenantAdminSerializer(tenant).data)


class AuditLogListView(APIView):
    """GET: recent audit log entries, optionally filtered by tenant_id."""

    permission_classes = [IsSuperAdminAuthenticated]

    def get(self, request):
        logs = AuditLog.objects.select_related("superadmin").all()
        tenant_id = request.query_params.get("tenant_id")
        if tenant_id:
            logs = logs.filter(target_tenant_id=tenant_id)
        return Response(AuditLogSerializer(logs[:200], many=True).data)