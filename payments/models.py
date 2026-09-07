from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
from core.models import TenantScopedModel


def _fernet():
    return Fernet(settings.RAZORPAY_TOKEN_ENCRYPTION_KEY.encode())


class RazorpayConnection(TenantScopedModel):
    """
    One per tenant. Tokens are encrypted at rest (Fernet, symmetric) - the
    OAuth flow only ever writes here via set_tokens(); nothing else in the
    codebase should read *_encrypted directly, always via get_access_token().
    """

    razorpay_account_id = models.CharField(max_length=100, blank=True, default="")
    access_token_encrypted = models.BinaryField()
    refresh_token_encrypted = models.BinaryField()
    token_expires_at = models.DateTimeField()
    connected_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

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