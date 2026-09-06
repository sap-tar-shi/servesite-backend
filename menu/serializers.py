from rest_framework import serializers
from .models import MenuCategory, MenuItem


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