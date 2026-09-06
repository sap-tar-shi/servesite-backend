from django.contrib import admin
from .models import SiteConfig, Page, Section, MediaAsset


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("tenant", "template_version", "status")
    list_filter = ("status",)


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("tenant", "page_type", "enabled")
    list_filter = ("page_type", "enabled")
    inlines = [SectionInline]


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("tenant", "storage_key", "media_type", "width", "height")