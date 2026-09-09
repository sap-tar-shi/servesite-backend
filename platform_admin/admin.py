from django.contrib import admin
from .models import SuperAdmin, AuditLog


@admin.register(SuperAdmin)
class SuperAdminAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "created_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "superadmin", "target_tenant_id", "created_at")
    list_filter = ("action",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]  # append-only - no manual edits via admin either

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False