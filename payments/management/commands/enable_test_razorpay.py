from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from payments.models import RazorpayConnection


class Command(BaseCommand):
    """
    Interim stand-in for the real OAuth connect flow (P2-T7), until
    Razorpay Partner approval comes through. Stores your single Test Mode
    key_id/key_secret exactly the way a real OAuth callback would store an
    access_token/refresh_token pair - P2-T8/T9's payment-charging code
    reads from RazorpayConnection either way, so nothing there needs to
    change when the real flow replaces this command.
    """

    help = "Simulate a Razorpay connection for a tenant using test-mode keys"

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True)

    def handle(self, *args, **options):
        tenant = Tenant.objects.get(slug=options["slug"])
        token = set_current_tenant(tenant)
        set_tenant_guc(tenant.id)
        try:
            connection, _ = RazorpayConnection.objects.get_or_create(tenant=tenant, defaults={
                "access_token_encrypted": b"", "refresh_token_encrypted": b"", "token_expires_at": timezone.now(),
            })
            connection.set_tokens(
                access_token=settings.RAZORPAY_TEST_KEY_ID,
                refresh_token=settings.RAZORPAY_TEST_KEY_SECRET,
                expires_at=timezone.now() + timedelta(days=3650),
            )
            connection.razorpay_account_id = "test-mode-single-account"
            connection.save(update_fields=["razorpay_account_id"])

            tenant.online_payment_enabled = True
            tenant.save(update_fields=["online_payment_enabled"])
            self.stdout.write(self.style.SUCCESS(f"Test-mode Razorpay connection enabled for {tenant.slug}"))
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)