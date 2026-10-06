import secrets
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.throttling import AnonRateThrottle
from .serializers import LoginSerializer, SignupSerializer
from .models import User, Membership, EmailVerificationToken
from .permissions import HasModulePermission
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from billing.services import enforce_count_limit, FeatureLimitExceeded
from tenants.services import provision_tenant, suggest_slugs, SlugTaken


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
        if not user.is_email_verified and not settings.SKIP_EMAIL_VERIFICATION:
            return Response(
                {"detail": "Please verify your email before signing in. Check your inbox for the verification link."},
                status=status.HTTP_403_FORBIDDEN,
            )
        login(request, user)
        return Response(_serialize_user_with_memberships(user))


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    permission_classes = [permissions.AllowAny]

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


class SignupRateThrottle(AnonRateThrottle):
    scope = "signup"


def _send_verification_email(user, token: str):
    verify_url = f"{settings.FRONTEND_APEX_URL}/verify-email?token={token}"
    send_mail(
        subject="Verify your ServeSite account",
        message=f"Click to verify your email and finish setting up your restaurant:\n\n{verify_url}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


class SignupView(APIView):
    """Public. Anyone who signs up is provisioned as the owner of a brand-new
    restaurant. If the email already exists, we don't silently attach a new
    tenant to it - they're told to log in instead."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [SignupRateThrottle]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(email=data["email"]).exists():
            return Response(
                {"detail": "An account with this email already exists. Log in instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tenant, owner_user, _owner_created, _temp_password = provision_tenant(
                slug=data["slug"], name=data["restaurant_name"],
                owner_email=data["email"], owner_password=data["password"],
            )
        except SlugTaken as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        owner_user.name = data["owner_name"]

        if settings.SKIP_EMAIL_VERIFICATION:
            owner_user.is_email_verified = True
            owner_user.save(update_fields=["name", "is_email_verified"])
            return Response({"tenant_slug": tenant.slug, "email_verification_required": False}, status=status.HTTP_201_CREATED)

        owner_user.save(update_fields=["name"])
        verification = EmailVerificationToken.objects.create(user=owner_user)
        _send_verification_email(owner_user, verification.token)
        return Response({"tenant_slug": tenant.slug, "email_verification_required": True}, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get("token", "")
        verification = EmailVerificationToken.objects.filter(token=token).select_related("user").first()
        if verification is None or not verification.is_valid():
            return Response({"detail": "This verification link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

        verification.used_at = timezone.now()
        verification.save(update_fields=["used_at"])
        verification.user.is_email_verified = True
        verification.user.save(update_fields=["is_email_verified"])

        membership = Membership.objects.filter(user=verification.user, role=Membership.ROLE_OWNER).select_related("tenant").first()
        return Response({"tenant_slug": membership.tenant.slug if membership else None})


class SlugSuggestionsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        name = request.query_params.get("name", "").strip()
        if not name:
            return Response({"suggestions": []})
        return Response({"suggestions": suggest_slugs(name)})


class SiteCustomizationView(APIView):
    permission_classes = [HasModulePermission("site_customization")]

    def get(self, request):
        return Response({"theme": "confidential-branding-data"})


class LiveOrdersView(APIView):
    permission_classes = [HasModulePermission("live_orders")]

    def get(self, request):
        return Response({"orders": ["confidential-order-data"]})


class BillingView(APIView):
    permission_classes = [HasModulePermission("billing_staff_domains")]

    def get(self, request):
        return Response({"billing": "confidential-billing-data"})


class StaffCredentialsView(APIView):
    """
    Owner-only (billing_staff_domains). GET reveals the shared staff
    login's email only - the password is never stored in plaintext or
    retrievable after creation. POST regenerates the password and returns
    it once in the response body; this is the ONLY way to obtain/share
    the current password. Per P2-T14 AC.
    """

    permission_classes = [HasModulePermission("billing_staff_domains")]

    def _get_shared_membership(self, request):
        return Membership.objects.filter(
            tenant=request.tenant, role=Membership.ROLE_STAFF, is_shared_account=True,
        ).select_related("user").first()

    def get(self, request):
        membership = self._get_shared_membership(request)
        if membership is None:
            return Response({"detail": "No shared staff account provisioned for this tenant."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"email": membership.user.email})

    def post(self, request):
        membership = self._get_shared_membership(request)
        if membership is None:
            return Response({"detail": "No shared staff account provisioned for this tenant."}, status=status.HTTP_404_NOT_FOUND)
        new_password = secrets.token_urlsafe(12)
        membership.user.set_password(new_password)
        membership.user.save()
        return Response({"email": membership.user.email, "password": new_password})


class InviteStaffView(APIView):
    """
    Owner-only (billing_staff_domains). Per P2-T15 AC.
    POST {"email": "..."} - invites a staff member:
      - new user -> creates User + Membership(role=staff), returns a
        one-time temp password (never stored/retrievable again after this).
      - existing user (already registered elsewhere) -> just attaches a
        Membership here; no password shown, since they already have one.
    GET - lists this tenant's individually-invited staff (is_shared_account=False),
    for the admin "Billing & Staff" page.
    """

    permission_classes = [HasModulePermission("billing_staff_domains")]

    def get(self, request):
        memberships = Membership.objects.filter(
            tenant=request.tenant, role=Membership.ROLE_STAFF, is_shared_account=False,
        ).select_related("user").order_by("created_at")
        return Response([
            {"email": m.user.email, "created_at": m.created_at}
            for m in memberships
        ])

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email=email).first()
        password_to_return = None
        if user is None:
            user = User.objects.create_user(email=email, password=secrets.token_urlsafe(12))
            password_to_return = None  # set below only after we know creation succeeded
            temp_password = secrets.token_urlsafe(12)
            user.set_password(temp_password)
            user.save()
            password_to_return = temp_password

        if Membership.objects.filter(user=user, tenant=request.tenant).exists():
            return Response({"detail": "This person already has a membership at this restaurant."}, status=status.HTTP_400_BAD_REQUEST)

        current_staff_count = Membership.objects.filter(
            tenant=request.tenant, role=Membership.ROLE_STAFF, is_shared_account=False,
        ).count()
        try:
            enforce_count_limit(
                request.tenant, limit_key="max_staff_accounts",
                current_count=current_staff_count, item_label="staff accounts",
            )
        except FeatureLimitExceeded as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        Membership.objects.create(
            user=user, tenant=request.tenant, role=Membership.ROLE_STAFF, is_shared_account=False,
        )

        response_data = {"email": user.email}
        if password_to_return:
            response_data["password"] = password_to_return
        return Response(response_data, status=status.HTTP_201_CREATED)


def _get_shared_staff_membership(tenant):
    """Shared helper - locates the auto-provisioned shared staff Membership for a tenant, if any."""
    return Membership.objects.filter(
        tenant=tenant, role=Membership.ROLE_STAFF, is_shared_account=True,
    ).select_related("user").first()


class StaffModeView(APIView):
    """
    Owner-only (billing_staff_domains). Per P2-T16 AC.
    GET  -> current staff_account_mode.
    POST {"mode": "shared"|"individual"} -> switches mode.
      - individual: deactivates the shared login (User.is_active=False) so
        it can no longer be used to log in going forward - staff must use
        their individual accounts from this point on.
      - shared: reactivates the shared login.
    Switching NEVER touches existing OrderEvent rows - actor is an
    immutable FK captured at write time, unaffected by any later toggle.
    """

    permission_classes = [HasModulePermission("billing_staff_domains")]

    def get(self, request):
        return Response({"staff_account_mode": request.tenant.staff_account_mode})

    def post(self, request):
        mode = request.data.get("mode")
        valid_modes = {choice[0] for choice in request.tenant.STAFF_MODE_CHOICES}
        if mode not in valid_modes:
            return Response({"detail": f"'mode' must be one of {sorted(valid_modes)}."}, status=status.HTTP_400_BAD_REQUEST)

        request.tenant.staff_account_mode = mode
        request.tenant.save(update_fields=["staff_account_mode"])

        shared_membership = _get_shared_staff_membership(request.tenant)
        if shared_membership is not None:
            shared_membership.user.is_active = (mode == request.tenant.STAFF_MODE_SHARED)
            shared_membership.user.save(update_fields=["is_active"])

        return Response({"staff_account_mode": request.tenant.staff_account_mode})