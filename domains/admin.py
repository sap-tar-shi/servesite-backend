from django.contrib import admin
from .models import Domain


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ["hostname", "tenant", "status", "verified_at", "activated_at"]
    list_filter = ["status"]
    readonly_fields = ["verification_token", "acm_certificate_arn"]