from rest_framework import serializers
from .models import Table


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ["id", "label", "table_token", "is_active", "created_at"]
        read_only_fields = ["id", "table_token", "created_at"]