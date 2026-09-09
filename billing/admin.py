from django.contrib import admin
from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "billing_interval", "is_active", "created_at")
    list_filter = ("billing_interval", "is_active")
    search_fields = ("name",)