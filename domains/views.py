from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import dns.resolver
from django.utils import timezone
from accounts.permissions import HasModulePermission
from billing.services import enforce_bool_flag, FeatureLimitExceeded
from .models import Domain
from .serializers import DomainSerializer, DomainCreateSerializer
from .aws_client import request_certificate
from .tasks import poll_single_domain_verification


class DomainView(APIView):
    """
    GET  /api/domains/  - current tenant's custom domain (or 404 if none)
    POST /api/domains/  - register a new custom domain, gated on the
                           tenant's plan (feature_limits.custom_domain_allowed,
                           P3-T1/P3-T4). Returns verification instructions;
                           does NOT request an ACM cert yet - that only
                           happens after DNS ownership is proven (see
                           DomainVerifyView), per P4-T4 AC ordering.
    """

    permission_classes = [HasModulePermission("site_customization")]

    def get(self, request):
        domain = Domain.objects.filter(tenant=request.tenant).first()
        if domain is None:
            return Response({"detail": "No custom domain configured."}, status=status.HTTP_404_NOT_FOUND)
        return Response(DomainSerializer(domain).data)

    def post(self, request):
        try:
            enforce_bool_flag(request.tenant, limit_key="custom_domain_allowed", feature_label="Custom domains")
        except FeatureLimitExceeded as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

        if Domain.objects.filter(tenant=request.tenant).exists():
            return Response(
                {"detail": "This tenant already has a custom domain configured. Remove it before adding another."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DomainCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        domain = Domain.objects.create(tenant=request.tenant, hostname=serializer.validated_data["hostname"])
        return Response(DomainSerializer(domain).data, status=status.HTTP_201_CREATED)


class DomainVerifyView(APIView):
    """
    POST /api/domains/verify/

    Owner-initiated "check now" - does an immediate DNS TXT lookup rather
    than waiting for the periodic Celery poll (domains/tasks.py). On
    success, kicks off ACM cert request and hands off to the periodic
    task for validation polling from here on (DNS TXT ownership proof and
    ACM cert issuance are two separate, sequential proofs - conflating
    them into one status transition would hide which step actually failed).
    """

    permission_classes = [HasModulePermission("site_customization")]

    def post(self, request):
        try:
            domain = Domain.objects.get(tenant=request.tenant)
        except Domain.DoesNotExist:
            return Response({"detail": "No custom domain configured."}, status=status.HTTP_404_NOT_FOUND)

        if domain.status != Domain.STATUS_PENDING_VERIFICATION:
            return Response(DomainSerializer(domain).data)  # already past this step - no-op

        record_name = f"_servesite-verify.{domain.hostname}"
        try:
            answers = dns.resolver.resolve(record_name, "TXT")
            found = any(domain.verification_token in b.decode() for rdata in answers for b in rdata.strings)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            found = False

        if not found:
            return Response(
                {"detail": f"TXT record not found or doesn't match yet at {record_name}. DNS changes can take time to propagate - try again shortly."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        domain.status = Domain.STATUS_VERIFIED
        domain.verified_at = timezone.now()
        domain.save(update_fields=["status", "verified_at"])

        acm_response = request_certificate(domain.hostname)
        domain.acm_certificate_arn = acm_response["CertificateArn"]
        domain.status = Domain.STATUS_ISSUING_CERT
        domain.save(update_fields=["acm_certificate_arn", "status"])

        poll_single_domain_verification.delay(str(domain.id))

        return Response(DomainSerializer(domain).data)


class PublicDomainResolveView(APIView):
    """
    GET /api/domains/resolve/?hostname=mycafe.com

    AllowAny - called by the Next.js middleware (frontend, not yet built as
    of this point) BEFORE any tenant is known, purely to answer "which
    tenant does this custom domain belong to." Deliberately uses
    Domain.unscoped: this lookup is inherently cross-tenant by nature (we
    don't know the tenant yet - that's the whole question), same category
    as the audited cross-tenant reads elsewhere in the platform. Only
    ACTIVE domains resolve - pending/failed domains 404, so an
    unverified/mid-issuance domain never accidentally serves traffic.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        hostname = request.query_params.get("hostname", "").strip().lower()
        if not hostname:
            return Response({"detail": "hostname query param is required."}, status=status.HTTP_400_BAD_REQUEST)

        domain = Domain.unscoped.filter(hostname=hostname, status=Domain.STATUS_ACTIVE).select_related("tenant").first()
        if domain is None:
            return Response({"detail": "No active custom domain found for this hostname."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"slug": domain.tenant.slug})