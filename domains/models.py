import uuid
import secrets
from django.db import models
from core.models import TenantScopedModel


def generate_verification_token():
    return secrets.token_hex(16)


class Domain(TenantScopedModel):
    """
    A tenant's custom domain (e.g. "mycafe.com"), on top of their default
    {slug}.platform.com subdomain (P1-T21) - never a replacement for it.
    Verification is a DNS TXT-record challenge, proving domain ownership
    before we request a cert or attach it to CloudFront - per architecture
    §6/P4-T4 AC: "verified custom domain serves the tenant's public site
    with valid TLS; admin never served on it" (that last clause is enforced
    at the routing layer, not here - see views.py note).
    """

    STATUS_PENDING_VERIFICATION = "pending_verification"
    STATUS_VERIFIED = "verified"          # DNS ownership proven, cert not yet issued
    STATUS_ISSUING_CERT = "issuing_cert"  # ACM cert requested, awaiting validation+issuance
    STATUS_ACTIVE = "active"              # cert issued + attached to CloudFront - serving traffic
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING_VERIFICATION, "Pending Verification"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_ISSUING_CERT, "Issuing Certificate"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hostname = models.CharField(max_length=253, unique=True)  # e.g. "mycafe.com" - globally unique across all tenants
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING_VERIFICATION)

    # DNS ownership challenge - owner must create a TXT record at
    # _servesite-verify.<hostname> with this value.
    verification_token = models.CharField(max_length=64, default=generate_verification_token)

    # ACM identifiers, populated once we've requested a cert (P4-T4 step 2)
    acm_certificate_arn = models.CharField(max_length=255, blank=True, default="")

    failure_reason = models.TextField(blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "domains_domain"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="one_custom_domain_per_tenant"),
        ]

    def __str__(self):
        return f"{self.hostname} ({self.status})"