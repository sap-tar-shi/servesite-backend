from decimal import Decimal
from .models import MenuItem, ModifierGroup


class CartPricingError(Exception):
    def __init__(self, detail):
        self.detail = detail


def price_cart_items(raw_items):
    """
    Shared by CartValidateView (P2-T3, stateless) and orders.OrderCreateView
    (P2-T4, persists the result). Raises CartPricingError with the same
    detail message either endpoint would have returned as a 400 - callers
    just catch it and translate to their own Response.
    """
    if not isinstance(raw_items, list) or not raw_items:
        raise CartPricingError("'items' must be a non-empty list.")

    priced_items = []
    subtotal = Decimal("0.00")

    for raw in raw_items:
        menu_item_id = raw.get("menu_item_id")
        quantity = raw.get("quantity")
        modifier_ids = raw.get("modifier_ids", [])

        if not menu_item_id or not isinstance(quantity, int) or quantity < 1:
            raise CartPricingError("Each item needs a valid menu_item_id and a positive integer quantity.")

        try:
            item = MenuItem.objects.select_related("category").get(id=menu_item_id)
        except MenuItem.DoesNotExist:
            raise CartPricingError(f"Menu item {menu_item_id} not found.")

        if not item.is_available:
            raise CartPricingError(f"'{item.name}' is currently unavailable.")

        linked_groups = ModifierGroup.objects.filter(items=item).prefetch_related("modifiers")
        valid_modifier_ids = {str(m.id) for g in linked_groups for m in g.modifiers.all()}

        for mid in modifier_ids:
            if str(mid) not in valid_modifier_ids:
                raise CartPricingError(f"Modifier {mid} is not valid for '{item.name}'.")

        for group in linked_groups:
            selected_in_group = [m for m in group.modifiers.all() if str(m.id) in {str(x) for x in modifier_ids}]
            count = len(selected_in_group)
            if count < group.min_select or count > group.max_select:
                raise CartPricingError(
                    f"'{group.name}' requires between {group.min_select} and {group.max_select} selections, got {count}.")

        selected_modifiers = [m for g in linked_groups for m in g.modifiers.all() if str(m.id) in {str(x) for x in modifier_ids}]
        unit_price = item.price + sum((m.price_delta for m in selected_modifiers), Decimal("0.00"))
        line_total = unit_price * quantity
        subtotal += line_total

        priced_items.append({
            "menu_item": item,
            "quantity": quantity,
            "modifiers": selected_modifiers,
            "unit_price": unit_price,
            "line_total": line_total,
        })

    return priced_items, subtotal