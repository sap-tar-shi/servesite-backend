from django.contrib import admin
from .models import MenuCategory, MenuItem


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 0
    fields = ("name", "price", "is_available", "ordered_position")


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("tenant", "name", "ordered_position", "visible")
    list_filter = ("visible",)
    inlines = [MenuItemInline]


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("tenant", "category", "name", "price", "is_available", "ordered_position")
    list_filter = ("is_available",)