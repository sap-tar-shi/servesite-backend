from django.contrib import admin
from .models import MenuCategory, MenuItem, ModifierGroup, Modifier


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


class ModifierInline(admin.TabularInline):
    model = Modifier
    extra = 0


@admin.register(ModifierGroup)
class ModifierGroupAdmin(admin.ModelAdmin):
    list_display = ("tenant", "name", "min_select", "max_select")
    filter_horizontal = ("items",)
    inlines = [ModifierInline]