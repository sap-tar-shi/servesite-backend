from django.contrib import admin
from .models import TemplateRegistry, TemplateVersion


class TemplateVersionInline(admin.TabularInline):
    model = TemplateVersion
    extra = 0
    readonly_fields = ("published_at",)


@admin.register(TemplateRegistry)
class TemplateRegistryAdmin(admin.ModelAdmin):
    list_display = ("display_name", "name", "status", "created_at")
    inlines = [TemplateVersionInline]


@admin.register(TemplateVersion)
class TemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version", "published_at")
    list_filter = ("template",)