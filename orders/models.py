from django.db import models
from core.models import TenantScopedModel
from menu.models import MenuItem
from tables.models import Table


class Order(TenantScopedModel):
    STATUS_CHOICES = [
        ("placed", "Placed"), ("accepted", "Accepted"), ("preparing", "Preparing"),
        ("ready", "Ready"), ("served", "Served"), ("handed_over", "Handed Over"),
        ("completed", "Completed"), ("paid", "Paid"), ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
    ]
    ORDER_TYPE_CHOICES = [("dine_in", "Dine-in"), ("takeaway", "Takeaway"), ("online", "Online")]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="placed")
    # order_type/table are nullable - P2-T5 resolves these from QR context;
    # this task only needs the columns to exist and hold whatever T5 writes.
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, null=True, blank=True)
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    address = models.CharField(max_length=500, blank=True, default="")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta(TenantScopedModel.Meta):
        db_table = "orders_order"

    def __str__(self):
        return f"{self.tenant.slug}/order-{str(self.id)[:8]}"


class OrderItem(TenantScopedModel):
    """
    Per AC: later menu edits never mutate historical orders. menu_item is
    a nullable reference (SET_NULL) purely for traceability/analytics -
    item_name/unit_price/modifiers_snapshot are the actual source of truth
    for what this order contains, captured at order-placement time and
    never re-read from MenuItem/Modifier afterward.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    item_name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
    modifiers_snapshot = models.JSONField(default=list, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "orders_order_item"

    def __str__(self):
        return f"{self.item_name} x{self.quantity}"