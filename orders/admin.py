from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("item_name", "unit_price", "quantity", "line_total", "modifiers_snapshot")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("tenant", "id", "status", "order_type", "subtotal", "created_at")
    list_filter = ("status", "order_type")
    inlines = [OrderItemInline]