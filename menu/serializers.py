from rest_framework import serializers
from .models import MenuCategory, MenuItem, ModifierGroup, Modifier


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ["id", "category", "name", "description", "price", "image",
                  "is_available", "ordered_position", "created_at"]
        read_only_fields = ["id", "created_at"]


class MenuCategorySerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = ["id", "name", "ordered_position", "visible", "items", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        """
        Explicit tenant-scoped uniqueness check. Needed because `tenant`
        isn't a serializer field (it's injected in the view's
        perform_create), so DRF can't auto-derive a validator for the
        unique_category_name_per_tenant DB constraint - without this,
        a duplicate name reaches the DB as a raw IntegrityError (500)
        instead of a clean 400.
        """
        qs = MenuCategory.objects.filter(name=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        return value

class PublicMenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ["name", "description", "price", "is_available"]


class PublicMenuCategorySerializer(serializers.ModelSerializer):
    items = PublicMenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = ["name", "items"]


class ModifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Modifier
        fields = ["id", "group", "name", "price_delta", "created_at"]
        read_only_fields = ["id", "created_at"]


class ModifierGroupSerializer(serializers.ModelSerializer):
    modifiers = ModifierSerializer(many=True, read_only=True)

    class Meta:
        model = ModifierGroup
        fields = ["id", "name", "min_select", "max_select", "items", "modifiers", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        min_select = data.get("min_select", getattr(self.instance, "min_select", 0))
        max_select = data.get("max_select", getattr(self.instance, "max_select", 1))
        if min_select > max_select:
            raise serializers.ValidationError("min_select cannot be greater than max_select.")
        return data