from rest_framework import serializers
from tenants.models import Tenant
from .models import AuditLog


class TenantAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "slug", "name", "status", "staff_account_mode", "online_payment_enabled", "created_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    superadmin_email = serializers.CharField(source="superadmin.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "superadmin_email", "action", "target_tenant_id", "details", "created_at"]