from django.contrib import admin
from .models import Table


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ("tenant", "label", "table_token", "is_active")
    list_filter = ("is_active",)