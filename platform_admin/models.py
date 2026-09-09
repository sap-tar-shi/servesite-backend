import uuid
from django.contrib.auth.hashers import make_password, check_password
from django.db import models


class SuperAdmin(models.Model):
    """
    Deliberately NOT accounts.User + a flag, and NOT Django's AUTH_USER_MODEL
    machinery - a fully separate identity per design doc §7.1/§12, so a bug
    in tenant auth can never leak into platform-operator access, and vice
    versa. Session-based, but keyed under its own session key
    ("superadmin_id"), never touching request.user.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_admin_superadmin"

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    def __str__(self):
        return self.email


class AuditLog(models.Model):
    """
    Every super-admin action that touches tenant state gets one row here.
    Append-only - no update/delete API is ever exposed for this model.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    superadmin = models.ForeignKey(SuperAdmin, on_delete=models.PROTECT, related_name="audit_logs")
    action = models.CharField(max_length=50)  # e.g. "tenant.create", "tenant.suspend"
    target_tenant_id = models.UUIDField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_admin_audit_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.superadmin.email} :: {self.action} :: {self.target_tenant_id}"