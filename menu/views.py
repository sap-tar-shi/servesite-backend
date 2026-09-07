from decimal import Decimal
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.permissions import HasModulePermission
from .models import MenuCategory, MenuItem, ModifierGroup, Modifier
from .serializers import (
    MenuCategorySerializer, MenuItemSerializer, PublicMenuCategorySerializer,
    ModifierGroupSerializer, ModifierSerializer,
)
from .tasks import revalidate_public_menu

class MenuCategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = MenuCategorySerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return MenuCategory.objects.all()

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)
        revalidate_public_menu.delay(self.request.tenant.slug)


class MenuCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MenuCategorySerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return MenuCategory.objects.all()
    
    def perform_update(self, serializer):
        serializer.save()
        revalidate_public_menu.delay(self.request.tenant.slug)

    def perform_destroy(self, instance):
        tenant_slug = self.request.tenant.slug
        instance.delete()
        revalidate_public_menu.delay(tenant_slug)


class MenuItemListCreateView(generics.ListCreateAPIView):
    serializer_class = MenuItemSerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        qs = MenuItem.objects.select_related("category").all()
        category_id = self.request.query_params.get("category")
        if category_id:
            qs = qs.filter(category_id=category_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class MenuItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MenuItemSerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return MenuItem.objects.all()

    def perform_update(self, serializer):
        serializer.save()
        revalidate_public_menu.delay(self.request.tenant.slug)

    def perform_destroy(self, instance):
        tenant_slug = self.request.tenant.slug
        instance.delete()
        revalidate_public_menu.delay(tenant_slug)


class PublicMenuView(generics.ListAPIView):
    """
    GET /api/menu/public/  - no auth required (diners aren't logged in).
    Returns only visible categories, per P1-T19/T20 AC. Unavailable items
    are still included (template dims them per design, doesn't hide them) -
    only category.visible=False is excluded entirely.
    """

    serializer_class = PublicMenuCategorySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return MenuCategory.objects.filter(visible=True).prefetch_related("items")


class ModifierGroupListCreateView(generics.ListCreateAPIView):
    serializer_class = ModifierGroupSerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return ModifierGroup.objects.prefetch_related("modifiers", "items").all()

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class ModifierGroupDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ModifierGroupSerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return ModifierGroup.objects.prefetch_related("modifiers", "items").all()


class ModifierListCreateView(generics.ListCreateAPIView):
    serializer_class = ModifierSerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        qs = Modifier.objects.all()
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class ModifierDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ModifierSerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return Modifier.objects.all()


class CartValidateView(APIView):
    """
    POST /api/menu/cart/validate/  - no auth (diners aren't logged in).

    Body: {"items": [{"menu_item_id": "...", "quantity": 2, "modifier_ids": ["...", "..."]}]}

    Client never sends a price - there's nothing to tamper with. Every
    price comes from the current DB row; every modifier selection is
    checked against that item's actual linked ModifierGroups and their
    min/max rules (fail-closed: unknown/unlinked modifier -> whole request
    rejected, not silently dropped).
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw_items = request.data.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            return Response({"detail": "'items' must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)

        priced_items = []
        subtotal = Decimal("0.00")

        for raw in raw_items:
            menu_item_id = raw.get("menu_item_id")
            quantity = raw.get("quantity")
            modifier_ids = raw.get("modifier_ids", [])

            if not menu_item_id or not isinstance(quantity, int) or quantity < 1:
                return Response(
                    {"detail": "Each item needs a valid menu_item_id and a positive integer quantity."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                item = MenuItem.objects.select_related("category").get(id=menu_item_id)
            except MenuItem.DoesNotExist:
                return Response({"detail": f"Menu item {menu_item_id} not found."}, status=status.HTTP_400_BAD_REQUEST)

            if not item.is_available:
                return Response({"detail": f"'{item.name}' is currently unavailable."}, status=status.HTTP_400_BAD_REQUEST)

            linked_groups = ModifierGroup.objects.filter(items=item).prefetch_related("modifiers")
            valid_modifier_ids = {str(m.id) for g in linked_groups for m in g.modifiers.all()}

            for mid in modifier_ids:
                if str(mid) not in valid_modifier_ids:
                    return Response(
                        {"detail": f"Modifier {mid} is not valid for '{item.name}'."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            for group in linked_groups:
                selected_in_group = [
                    m for m in group.modifiers.all() if str(m.id) in {str(x) for x in modifier_ids}
                ]
                count = len(selected_in_group)
                if count < group.min_select or count > group.max_select:
                    return Response(
                        {"detail": f"'{group.name}' requires between {group.min_select} and {group.max_select} selections, got {count}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            selected_modifiers = [m for g in linked_groups for m in g.modifiers.all() if str(m.id) in {str(x) for x in modifier_ids}]
            unit_price = item.price + sum((m.price_delta for m in selected_modifiers), Decimal("0.00"))
            line_total = unit_price * quantity
            subtotal += line_total

            priced_items.append({
                "menu_item_id": str(item.id),
                "name": item.name,
                "quantity": quantity,
                "modifiers": [{"id": str(m.id), "name": m.name, "price_delta": str(m.price_delta)} for m in selected_modifiers],
                "unit_price": str(unit_price),
                "line_total": str(line_total),
            })

        return Response({"items": priced_items, "subtotal": str(subtotal)})