from rest_framework import serializers
from .models import Domain


class DomainSerializer(serializers.ModelSerializer):
    verify_record_name = serializers.SerializerMethodField()

    class Meta:
        model = Domain
        fields = [
            "id", "hostname", "status", "verification_token",
            "verify_record_name", "failure_reason", "verified_at", "activated_at",
        ]
        read_only_fields = ["status", "verification_token", "failure_reason", "verified_at", "activated_at"]

    def get_verify_record_name(self, obj):
        # The exact TXT record name the owner must create at their DNS
        # provider - surfaced here so the admin UI never has to hardcode
        # the "_servesite-verify." prefix separately from the backend.
        return f"_servesite-verify.{obj.hostname}"


class DomainCreateSerializer(serializers.Serializer):
    hostname = serializers.CharField(max_length=253)

    def validate_hostname(self, value):
        value = value.strip().lower()
        if value.startswith("http://") or value.startswith("https://") or "/" in value:
            raise serializers.ValidationError("Enter a bare domain (e.g. mycafe.com), not a URL.")
        if Domain.unscoped.filter(hostname=value).exists():
            raise serializers.ValidationError("This domain is already registered on the platform.")
        return value