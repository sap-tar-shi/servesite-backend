from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
from core.models import TenantScopedModel


def _fernet():
    return Fernet(settings.RAZORPAY_TOKEN_ENCRYPTION_KEY.encode())


class RazorpayConnection(TenantScopedModel):
    razorpay_account_id = models.CharField(max_length=100, blank=True, default="")
    access_token_encrypted = models.BinaryField()
    refresh_token_encrypted = models.BinaryField()
    token_expires_at = models.DateTimeField()
    connected_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    auth_mode = models.CharField(max_length=20, choices=[("oauth", "OAuth"), ("direct_keys", "Direct Keys")], default="direct_keys")
    webhook_secret = models.CharField(max_length=100, blank=True, default="")

    class Meta(TenantScopedModel.Meta):
        db_table = "payments_razorpay_connection"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="unique_razorpay_connection_per_tenant"),
        ]

    def set_tokens(self, access_token, refresh_token, expires_at):
        f = _fernet()
        self.access_token_encrypted = f.encrypt(access_token.encode())
        self.refresh_token_encrypted = f.encrypt(refresh_token.encode())
        self.token_expires_at = expires_at
        self.save()

    def get_access_token(self):
        return _fernet().decrypt(bytes(self.access_token_encrypted)).decode()

    def get_refresh_token(self):
        return _fernet().decrypt(bytes(self.refresh_token_encrypted)).decode()

    def get_auth_header(self):
        if self.auth_mode == "oauth":
            return {"Authorization": f"Bearer {self.get_access_token()}"}
        import base64
        creds = f"{self.get_access_token()}:{self.get_refresh_token()}"
        b64 = base64.b64encode(creds.encode()).decode()
        return {"Authorization": f"Basic {b64}"}

    def __str__(self):
        return f"{self.tenant.slug} razorpay connection"


class RazorpayConnectAttempt(TenantScopedModel):
    """
    Short-lived record bridging the gap between 'owner clicked connect on
    their tenant subdomain' and 'Razorpay redirects back to one fixed
    platform-level callback URL with no tenant context of its own' - state
    is the only thing tying the callback back to the right tenant.
    """

    state = models.CharField(max_length=64, unique=True)
    consumed = models.BooleanField(default=False)

    class Meta(TenantScopedModel.Meta):
        db_table = "payments_razorpay_connect_attempt"


class Payment(TenantScopedModel):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="payment")
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(max_length=20, choices=[("created", "Created"), ("captured", "Captured"), ("failed", "Failed")], default="created")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta(TenantScopedModel.Meta):
        db_table = "payments_payment"


class WebhookEvent(TenantScopedModel):
    """
    Idempotency ledger - Razorpay may deliver the same webhook more than
    once; event_id being unique means a duplicate delivery is a no-op,
    never a double-apply.
    """

    event_id = models.CharField(max_length=150, unique=True)
    event_type = models.CharField(max_length=50)

    class Meta(TenantScopedModel.Meta):
        db_table = "payments_webhook_event"