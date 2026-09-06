from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from accounts.permissions import HasModulePermission
from .models import SiteConfig, Section
from .manifest import filter_to_whitelisted_fields, NonWhitelistedFieldError, get_editable_fields


class SiteContentUpdateView(APIView):
    """
    PATCH /api/cms/site-content/

    Body: {"section_type": "hero", "fields": {"headline": "New headline"}}

    Enforces per architecture §6: only manifest-declared editable_fields
    may be written. Any other field in the request causes the WHOLE
    request to be rejected with 403 (fail-closed), per P1-T17 AC.
    """

    permission_classes = [HasModulePermission("site_customization")]

    def patch(self, request):
        section_type = request.data.get("section_type")
        fields = request.data.get("fields", {})

        if not section_type or not isinstance(fields, dict):
            return Response(
                {"detail": "Request must include 'section_type' and a 'fields' object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            site_config = SiteConfig.objects.select_related("template_version").get()
        except SiteConfig.DoesNotExist:
            return Response({"detail": "No site config for this tenant."}, status=status.HTTP_404_NOT_FOUND)

        try:
            validated_fields = filter_to_whitelisted_fields(site_config, fields)
        except NonWhitelistedFieldError as e:
            return Response(
                {
                    "detail": "One or more fields are not editable for this template.",
                    "rejected_fields": list(e.rejected_fields),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        section, _ = Section.objects.get_or_create(
            tenant=request.tenant,
            page__page_type="landing",
            section_type=section_type,
            defaults={"content": {}},
        )
        section.content.update(validated_fields)
        section.save(update_fields=["content"])

        return Response({"section_type": section_type, "content": section.content})


class EditableFieldsView(APIView):
    """
    GET /api/cms/editable-fields/

    Returns the manifest's editable_fields list for this tenant's pinned
    template version - the admin UI reads this to know which controls to
    render at all (P1-T25's admin shell will consume this).
    """

    permission_classes = [HasModulePermission("site_customization")]

    def get(self, request):
        try:
            site_config = SiteConfig.objects.select_related("template_version").get()
        except SiteConfig.DoesNotExist:
            return Response({"detail": "No site config for this tenant."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"editable_fields": sorted(get_editable_fields(site_config))})