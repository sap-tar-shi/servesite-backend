from rest_framework import serializers
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "item_name", "unit_price", "quantity", "line_total", "modifiers_snapshot"]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "status", "order_type", "table", "address", "payment_mode", "subtotal", "items", "created_at"]
        read_only_fields = fields