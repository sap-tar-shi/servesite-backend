"""
Raw boto3 calls for custom-domain TLS (P4-T4). Matches the existing
platform convention (billing/razorpay_client.py) of thin wrapper functions
around the provider SDK, rather than a heavier abstraction - callers get
plain dicts back, error handling stays in views.py/tasks.py.
"""
import boto3
from django.conf import settings


def _acm_client():
    # CloudFront ONLY accepts ACM certs issued in us-east-1, regardless of
    # which region the rest of the stack runs in - hence the dedicated
    # AWS_ACM_REGION setting, not the app's general AWS_REGION.
    return boto3.client("acm", region_name=settings.AWS_ACM_REGION)


def _cloudfront_client():
    return boto3.client("cloudfront")


def request_certificate(hostname: str) -> dict:
    """
    Requests a DNS-validated ACM cert for `hostname`. Returns the raw ACM
    response, which includes CertificateArn. DNS validation records aren't
    in this response - a separate describe_certificate call (below) is
    needed once ACM has generated them (usually a few seconds later).
    """
    client = _acm_client()
    return client.request_certificate(
        DomainName=hostname,
        ValidationMethod="DNS",
    )


def describe_certificate(certificate_arn: str) -> dict:
    """
    Returns the full certificate description, including DomainValidationOptions
    (the CNAME record ACM wants) once populated, and Status
    ("PENDING_VALIDATION" / "ISSUED" / "FAILED" / etc).
    """
    client = _acm_client()
    return client.describe_certificate(CertificateArn=certificate_arn)


def attach_certificate_to_distribution(certificate_arn: str, hostname: str) -> dict:
    """
    Adds `hostname` as an alternate domain name (CNAME) on the platform's
    CloudFront distribution and points its viewer certificate at the newly
    issued cert. Requires CLOUDFRONT_DISTRIBUTION_ID to be set (only true
    once actually deployed - see P4-T4 checkpoint note on the deploy-time
    gap). Uses get_distribution_config + update_distribution's required
    If-Match ETag pattern, per CloudFront API.
    """
    client = _cloudfront_client()
    current = client.get_distribution_config(Id=settings.CLOUDFRONT_DISTRIBUTION_ID)
    config = current["DistributionConfig"]
    etag = current["ETag"]

    aliases = config.get("Aliases", {"Quantity": 0, "Items": []})
    if hostname not in aliases.get("Items", []):
        aliases["Items"] = aliases.get("Items", []) + [hostname]
        aliases["Quantity"] = len(aliases["Items"])
    config["Aliases"] = aliases

    config["ViewerCertificate"] = {
        "ACMCertificateArn": certificate_arn,
        "SSLSupportMethod": "sni-only",
        "MinimumProtocolVersion": "TLSv1.2_2021",
    }

    return client.update_distribution(
        Id=settings.CLOUDFRONT_DISTRIBUTION_ID,
        IfMatch=etag,
        DistributionConfig=config,
    )