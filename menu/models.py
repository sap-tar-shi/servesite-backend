from django.db import models
from core.models import TenantScopedModel


class MenuCategory(TenantScopedModel):
    name = models.CharField(max_length=200)
    ordered_position = models.PositiveIntegerField(default=0)
    visible = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "menu_category"
        indexes = TenantScopedModel.Meta.indexes + [
            models.Index(fields=["tenant", "ordered_position"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_category_name_per_tenant"),
        ]
        ordering = ["ordered_position"]

    def __str__(self):
        return f"{self.tenant.slug}/{self.name}"


class MenuItem(TenantScopedModel):
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ForeignKey(
        "cms.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_available = models.BooleanField(default=True)
    ordered_position = models.PositiveIntegerField(default=0)

    class Meta(TenantScopedModel.Meta):
        db_table = "menu_item"
        indexes = TenantScopedModel.Meta.indexes + [
            models.Index(fields=["tenant", "category", "ordered_position"]),
        ]
        ordering = ["ordered_position"]

    def __str__(self):
        return f"{self.tenant.slug}/{self.category.name}/{self.name}"