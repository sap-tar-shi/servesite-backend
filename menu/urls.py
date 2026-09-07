from django.urls import path
from .views import (
    MenuCategoryListCreateView, MenuCategoryDetailView,
    MenuItemListCreateView, MenuItemDetailView, PublicMenuView,
    ModifierGroupListCreateView, ModifierGroupDetailView,
    ModifierListCreateView, ModifierDetailView,
)

urlpatterns = [
    path("categories/", MenuCategoryListCreateView.as_view(), name="menu-category-list-create"),
    path("categories/<uuid:pk>/", MenuCategoryDetailView.as_view(), name="menu-category-detail"),
    path("items/", MenuItemListCreateView.as_view(), name="menu-item-list-create"),
    path("items/<uuid:pk>/", MenuItemDetailView.as_view(), name="menu-item-detail"),
    path("public/", PublicMenuView.as_view(), name="menu-public"),
    path("modifier-groups/", ModifierGroupListCreateView.as_view(), name="modifier-group-list-create"),
    path("modifier-groups/<uuid:pk>/", ModifierGroupDetailView.as_view(), name="modifier-group-detail"),
    path("modifiers/", ModifierListCreateView.as_view(), name="modifier-list-create"),
    path("modifiers/<uuid:pk>/", ModifierDetailView.as_view(), name="modifier-detail"),
]