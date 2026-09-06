from django.urls import path
from .views import (
    MenuCategoryListCreateView, MenuCategoryDetailView,
    MenuItemListCreateView, MenuItemDetailView,
)

urlpatterns = [
    path("categories/", MenuCategoryListCreateView.as_view(), name="menu-category-list-create"),
    path("categories/<uuid:pk>/", MenuCategoryDetailView.as_view(), name="menu-category-detail"),
    path("items/", MenuItemListCreateView.as_view(), name="menu-item-list-create"),
    path("items/<uuid:pk>/", MenuItemDetailView.as_view(), name="menu-item-detail"),
]