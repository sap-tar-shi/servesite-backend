from rest_framework import generics, permissions
from accounts.permissions import HasModulePermission
from .models import MenuCategory, MenuItem
from .serializers import MenuCategorySerializer, MenuItemSerializer, PublicMenuCategorySerializer


class MenuCategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = MenuCategorySerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return MenuCategory.objects.all()

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class MenuCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MenuCategorySerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return MenuCategory.objects.all()


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