from rest_framework import serializers
from .models import TemplateRegistry, TemplateVersion


class TemplateVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateVersion
        fields = ["id", "version", "capability_manifest", "changelog", "published_at"]


class TemplateRegistrySerializer(serializers.ModelSerializer):
    versions = TemplateVersionSerializer(many=True, read_only=True)

    class Meta:
        model = TemplateRegistry
        fields = ["id", "name", "display_name", "preview_image", "status", "created_at", "versions"]


class TemplateRegistryWriteSerializer(serializers.ModelSerializer):
    """Separate from the read serializer since create/update shouldn't accept nested versions."""

    class Meta:
        model = TemplateRegistry
        fields = ["name", "display_name", "preview_image", "status"]