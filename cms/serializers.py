from rest_framework import serializers
from .models import SiteConfig, Section, BlogPost


class ContentUpdateSerializer(serializers.Serializer):
    """
    Accepts an arbitrary dict of field_name -> value. Validation of WHICH
    fields are allowed happens in the view (against the manifest), not here -
    this serializer only validates shape (must be a flat dict).
    """

    fields = serializers.DictField()


class BlogPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = ["id", "title", "slug", "excerpt", "content", "cover_image", "status", "published_at"]
        read_only_fields = ["id"]