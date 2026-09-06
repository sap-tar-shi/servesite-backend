from rest_framework import serializers
from .models import SiteConfig, Section


class ContentUpdateSerializer(serializers.Serializer):
    """
    Accepts an arbitrary dict of field_name -> value. Validation of WHICH
    fields are allowed happens in the view (against the manifest), not here -
    this serializer only validates shape (must be a flat dict).
    """

    fields = serializers.DictField()