from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from accounts.permissions import HasModulePermission
from .tasks import generate_thumbnail
from .models import SiteConfig, Section, MediaAsset
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


class SiteContentView(APIView):
    """
    GET /api/cms/site-content/?section_type=hero

    Returns the CURRENT content for one section, so the admin edit form
    has something to populate fields with. Added as a Phase-3-frontend-pass
    prerequisite - SiteContentUpdateView is PATCH-only and EditableFieldsView
    only returns field NAMES, not current values; neither lets a form
    pre-fill itself, which FE-7 needs.
    """

    permission_classes = [HasModulePermission("site_customization")]

    def get(self, request):
        section_type = request.query_params.get("section_type")
        if not section_type:
            return Response({"detail": "section_type query param is required."}, status=status.HTTP_400_BAD_REQUEST)

        section = Section.objects.filter(page__page_type="landing", section_type=section_type).first()
        return Response({"section_type": section_type, "content": section.content if section else {}})


class AllSiteContentView(APIView):
    """
    GET /api/cms/site-content/all/ - every section's content in one call,
    keyed by section_type. Lets the FE-7 page render one form per section
    without N+1 requests (one per editable section).
    """

    permission_classes = [HasModulePermission("site_customization")]

    def get(self, request):
        sections = Section.objects.filter(page__page_type="landing")
        return Response({s.section_type: s.content for s in sections})


class MediaUploadView(APIView):
    """
    POST /api/cms/media/  (multipart/form-data, field name "file")

    Stores the file in S3 (via Django's configured storage backend, P0-T7),
    creates a MediaAsset row scoped to the current tenant, and kicks off
    async thumbnailing. Returns the CDN URL immediately - the thumbnail
    URL populates a moment later once the Celery task completes.
    """

    permission_classes = [HasModulePermission("site_customization")]
    parser_classes = [MultiPartParser]

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        from django.core.files.storage import default_storage
        storage_key = f"tenants/{request.tenant.slug}/{uploaded_file.name}"
        saved_path = default_storage.save(storage_key, uploaded_file)
        url = default_storage.url(saved_path)

        asset = MediaAsset.objects.create(
            tenant=request.tenant,
            storage_key=saved_path,
            url=url,
            media_type=MediaAsset.TYPE_IMAGE,
        )

        generate_thumbnail.delay(str(asset.id))

        return Response(
            {"id": str(asset.id), "url": asset.url, "thumbnail_url": asset.thumbnail_url},
            status=status.HTTP_201_CREATED,
        )