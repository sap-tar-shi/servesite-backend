from django.db import models
from core.models import TenantScopedModel
from menu.models import MenuItem
from tables.models import Table


TRANSITIONS = {
    "placed": {"accepted", "cancelled"},
    "accepted": {"preparing", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"served", "handed_over", "cancelled"},
    "served": {"completed", "paid"},
    "handed_over": {"completed", "paid"},
    "paid": {"completed", "refunded"},
    "completed": {"refunded"},
    "cancelled": set(),
    "refunded": set(),
}


class Order(TenantScopedModel):
    STATUS_CHOICES = [
        ("placed", "Placed"), ("accepted", "Accepted"), ("preparing", "Preparing"),
        ("ready", "Ready"), ("served", "Served"), ("handed_over", "Handed Over"),
        ("completed", "Completed"), ("paid", "Paid"), ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
    ]
    ORDER_TYPE_CHOICES = [("dine_in", "Dine-in"), ("takeaway", "Takeaway"), ("online", "Online")]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="placed")
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, null=True, blank=True)
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    address = models.CharField(max_length=500, blank=True, default="")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(
        max_length=20, choices=[("pay_now", "Pay Now"), ("pay_at_counter", "Pay at Counter")],
        null=True, blank=True,
    )    

    class Meta(TenantScopedModel.Meta):
        db_table = "orders_order"

    def __str__(self):
        return f"{self.tenant.slug}/order-{str(self.id)[:8]}"

    def transition_to(self, new_status, actor=None):
        if new_status not in TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Cannot transition from '{self.status}' to '{new_status}'.")

        if new_status == "served" and self.order_type != "dine_in":
            raise ValueError("'served' only applies to dine_in orders.")
        if new_status == "handed_over" and self.order_type not in ("takeaway", "online"):
            raise ValueError("'handed_over' only applies to takeaway/online orders.")

        old_status = self.status
        self.status = new_status
        self.save(update_fields=["status"])
        OrderEvent.objects.create(
            tenant=self.tenant, order=self, from_status=old_status, to_status=new_status, actor=actor,
        )


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


class OrderEvent(TenantScopedModel):
    """
    Audit trail per AC: every transition writes an event with actor +
    timestamp (created_at, inherited). actor is nullable - the very first
    event (creation -> placed) has no authenticated actor since diners
    aren't logged in.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta(TenantScopedModel.Meta):
        db_table = "orders_order_event"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order_id}: {self.from_status or '(new)'} -> {self.to_status}"