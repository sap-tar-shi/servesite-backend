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

class ModifierGroup(TenantScopedModel):
    """
    Reusable across items (e.g. a "Size" group shared by every pizza),
    per design doc §7.5's "item_id (or reusable)" - M2M to MenuItem rather
    than a single owning FK. min_select/max_select define the selection
    rule; actual enforcement at order time is P2-T3's job - this model
    only guarantees the rule itself is internally consistent.
    """

    name = models.CharField(max_length=100)
    min_select = models.PositiveIntegerField(default=0)
    max_select = models.PositiveIntegerField(default=1)
    items = models.ManyToManyField(MenuItem, related_name="modifier_groups", blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "menu_modifier_group"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_modifier_group_name_per_tenant"),
        ]

    def __str__(self):
        return f"{self.tenant.slug}/{self.name}"


class Modifier(TenantScopedModel):
    group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name="modifiers")
    name = models.CharField(max_length=100)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta(TenantScopedModel.Meta):
        db_table = "menu_modifier"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "group", "name"], name="unique_modifier_name_per_group"),
        ]

    def __str__(self):
        return f"{self.group.name}/{self.name}"