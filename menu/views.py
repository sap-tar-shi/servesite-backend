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
from .pricing import price_cart_items, CartPricingError

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
        return MenuCategory.objects.filter(visible=True).prefetch_related("items", "items__modifier_groups__modifiers")


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
    Client never sends a price - there's nothing to tamper with. Pricing
    logic lives in menu/pricing.py (shared with orders.OrderCreateView).
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            priced_items, subtotal = price_cart_items(request.data.get("items"))
        except CartPricingError as e:
            return Response({"detail": e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "items": [{
                "menu_item_id": str(p["menu_item"].id),
                "name": p["menu_item"].name,
                "quantity": p["quantity"],
                "modifiers": [{"id": str(m.id), "name": m.name, "price_delta": str(m.price_delta)} for m in p["modifiers"]],
                "unit_price": str(p["unit_price"]),
                "line_total": str(p["line_total"]),
            } for p in priced_items],
            "subtotal": str(subtotal),
        })