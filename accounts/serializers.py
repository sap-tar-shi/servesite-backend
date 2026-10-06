import re
from rest_framework import serializers

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class SignupSerializer(serializers.Serializer):
    restaurant_name = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=63)
    owner_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_slug(self, value):
        value = value.strip().lower()
        if not SLUG_RE.match(value):
            raise serializers.ValidationError("Use lowercase letters, numbers, and hyphens only (e.g. joes-diner).")
        if value in {"www", "admin", "api", "app"}:
            raise serializers.ValidationError("That address is reserved.")
        return value