from django.utils import timezone
from django.conf import settings
from django.utils.text import slugify
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from accounts.permissions import HasModulePermission
from .tasks import generate_thumbnail, revalidate_public_site
from .models import SiteConfig, Section, MediaAsset, BlogPost
from .serializers import ContentUpdateSerializer, BlogPostSerializer
from .manifest import filter_to_whitelisted_fields, NonWhitelistedFieldError, get_editable_fields
from billing.services import enforce_bool_flag, FeatureLimitExceeded
from templates_registry.models import TemplateVersion, TemplateRegistry
from templates_registry.serializers import TemplateVersionSerializer, TemplateRegistryWithLatestVersionSerializer


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
        revalidate_public_site.delay(request.tenant.slug)

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


class PublicSiteContentView(APIView):
    """
    GET /api/cms/public/site-content/ - AllowAny, shapes cms.Section rows
    into exactly the SiteContent JSON shape templates/classic-bistro/types.ts
    expects. This adapter layer exists because admin-facing field names
    (about_text) don't necessarily match template prop names (text) -
    keeping that translation here means the manifest/admin form can use
    whatever names make sense for editing, without the template needing to
    change. Falls back to empty-but-valid values if a tenant has no
    Section rows yet (new tenant, nothing customized).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        sections = {s.section_type: s.content for s in Section.objects.filter(page__page_type="landing")}
        hero = sections.get("hero", {})
        about = sections.get("about", {})
        contact = sections.get("contact", {})

        return Response({
            "restaurant_name": hero.get("restaurant_name", request.tenant.name),
            "logo": hero.get("logo"),
            "hero": {
                "headline": hero.get("headline", ""),
                "tagline": hero.get("tagline", ""),
                "hero_image": hero.get("hero_image"),
            },
            "about": {
                "text": about.get("about_text", ""),
            },
            "contact": {
                "address": contact.get("address", ""),
                "phone": contact.get("phone", ""),
                "opening_hours": contact.get("opening_hours", ""),
            },
        })

class AvailableUpgradeView(APIView):
    """
    GET /api/cms/template/available-upgrade/

    Returns the next newer TemplateVersion in the SAME template family as
    the tenant's currently pinned version, if one exists - or null. Per
    P4-T2 AC: this is read-only discovery; nothing changes until the owner
    explicitly calls TemplateUpgradeView below.
    """

    permission_classes = [HasModulePermission("site_customization")]

    def get(self, request):
        site_config = SiteConfig.objects.select_related(
            "template_version__template"
        ).get(tenant=request.tenant)
        current = site_config.template_version

        newer = (
            TemplateVersion.objects.filter(
                template=current.template,
                template__status="active",
                sequence__gt=current.sequence,
            )
            .order_by("-sequence")
            .first()
        )

        return Response({
            "current_version": TemplateVersionSerializer(current).data,
            "available_upgrade": TemplateVersionSerializer(newer).data if newer else None,
        })


class TemplateUpgradeView(APIView):
    """
    POST /api/cms/template/upgrade/
    Body: {"template_version_id": "<uuid>"}

    Re-pins SiteConfig.template_version to a newer version WITHIN THE SAME
    template family. Rejects (400) any target that is a different template
    family (that's P4-T3's job, not this endpoint's) or is not strictly
    newer than the currently pinned version (no accidental downgrades).
    Content is untouched - only the FK changes, per arch §6.
    """

    permission_classes = [HasModulePermission("site_customization")]

    def post(self, request):
        target_id = request.data.get("template_version_id")
        if not target_id:
            return Response({"detail": "template_version_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        site_config = SiteConfig.objects.select_related(
            "template_version__template"
        ).get(tenant=request.tenant)
        current = site_config.template_version

        try:
            target = TemplateVersion.objects.select_related("template").get(id=target_id)
        except TemplateVersion.DoesNotExist:
            return Response({"detail": "Template version not found."}, status=status.HTTP_404_NOT_FOUND)

        if target.template_id != current.template_id:
            return Response(
                {"detail": "Target version belongs to a different template family. Use the template switch flow instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if target.sequence <= current.sequence:
            return Response(
                {"detail": "Target version is not newer than the currently pinned version."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        site_config.template_version = target
        site_config.save(update_fields=["template_version"])
        revalidate_public_site.delay(request.tenant.slug)

        return Response(TemplateVersionSerializer(target).data)


class AvailableTemplatesView(APIView):
    """
    GET /api/cms/template/available-templates/

    Lists every OTHER active template family (excludes the tenant's
    currently pinned family - that's not a "switch"), each with its latest
    version, for a template-picker UI. P4-T3.
    """

    permission_classes = [HasModulePermission("site_customization")]

    def get(self, request):
        site_config = SiteConfig.objects.select_related("template_version__template").get(tenant=request.tenant)
        current_family_id = site_config.template_version.template_id

        families = TemplateRegistry.objects.filter(status="active").exclude(id=current_family_id)
        return Response(TemplateRegistryWithLatestVersionSerializer(families, many=True).data)


class TemplateSwitchView(APIView):
    """
    POST /api/cms/template/switch/
    Body: {"template_id": "<TemplateRegistry uuid>"}

    Re-pins SiteConfig.template_version to the LATEST active version of a
    DIFFERENT template family. Content (cms.Section rows) is untouched -
    per arch §6, content is stored independent of template, so nothing
    needs migrating; the new template simply renders whatever of it its
    own manifest declares. Rejects switching to the tenant's own current
    family (400) - use TemplateUpgradeView for that instead.
    """

    permission_classes = [HasModulePermission("site_customization")]

    def post(self, request):
        target_family_id = request.data.get("template_id")
        if not target_family_id:
            return Response({"detail": "template_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        site_config = SiteConfig.objects.select_related("template_version__template").get(tenant=request.tenant)
        current_family_id = site_config.template_version.template_id

        if str(target_family_id) == str(current_family_id):
            return Response(
                {"detail": "Already on this template family. Use the upgrade flow for a newer version of the same template."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_family = TemplateRegistry.objects.get(id=target_family_id, status="active")
        except TemplateRegistry.DoesNotExist:
            return Response({"detail": "Template not found or not active."}, status=status.HTTP_404_NOT_FOUND)

        latest_version = target_family.versions.order_by("-sequence").first()
        if latest_version is None:
            return Response({"detail": "Target template has no published versions."}, status=status.HTTP_400_BAD_REQUEST)

        site_config.template_version = latest_version
        site_config.save(update_fields=["template_version"])
        revalidate_public_site.delay(request.tenant.slug)

        return Response(TemplateVersionSerializer(latest_version).data)



class BlogPostListCreateView(APIView):
    """
    GET  /api/cms/blog/       - all posts (draft + published) for the admin list view
    POST /api/cms/blog/       - create a post, gated on feature_limits.blog_allowed (P3-T1)

    Note: gating happens on CREATE only, not on later edits/publishing of
    an already-existing post - if an owner downgrades plans after already
    having posts, those posts aren't retroactively deleted, matching the
    "content is never destroyed by a plan change" convention already
    established for other limits in this codebase.
    """

    permission_classes = [HasModulePermission("blog_management")]

    def get(self, request):
        posts = BlogPost.objects.all()
        return Response(BlogPostSerializer(posts, many=True).data)

    def post(self, request):
        try:
            enforce_bool_flag(request.tenant, limit_key="blog_allowed", feature_label="Blog")
        except FeatureLimitExceeded as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()
        if not data.get("slug") and data.get("title"):
            data["slug"] = slugify(data["title"])

        serializer = BlogPostSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        post = serializer.save(tenant=request.tenant)

        if post.status == BlogPost.STATUS_PUBLISHED and post.published_at is None:
            post.published_at = timezone.now()
            post.save(update_fields=["published_at"])
            revalidate_public_site.delay(request.tenant.slug)

        return Response(BlogPostSerializer(post).data, status=status.HTTP_201_CREATED)


class BlogPostDetailView(APIView):
    """
    GET/PATCH/DELETE /api/cms/blog/<uuid:post_id>/

    No feature-gate check here (see note on BlogPostListCreateView above) -
    only creation is gated.
    """

    permission_classes = [HasModulePermission("blog_management")]

    def get_object(self, request, post_id):
        return BlogPost.objects.get(id=post_id)

    def get(self, request, post_id):
        try:
            post = self.get_object(request, post_id)
        except BlogPost.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BlogPostSerializer(post).data)

    def patch(self, request, post_id):
        try:
            post = self.get_object(request, post_id)
        except BlogPost.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        was_published = post.status == BlogPost.STATUS_PUBLISHED
        serializer = BlogPostSerializer(post, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        post = serializer.save()

        just_published = not was_published and post.status == BlogPost.STATUS_PUBLISHED
        if just_published and post.published_at is None:
            post.published_at = timezone.now()
            post.save(update_fields=["published_at"])

        revalidate_public_site.delay(request.tenant.slug)
        return Response(BlogPostSerializer(post).data)

    def delete(self, request, post_id):
        try:
            post = self.get_object(request, post_id)
        except BlogPost.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        post.delete()
        revalidate_public_site.delay(request.tenant.slug)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicBlogListView(APIView):
    """
    GET /api/cms/public/blog/ - AllowAny, PUBLISHED posts only, newest first.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        posts = BlogPost.objects.filter(status=BlogPost.STATUS_PUBLISHED).order_by("-published_at")
        return Response(BlogPostSerializer(posts, many=True).data)


class PublicBlogDetailView(APIView):
    """
    GET /api/cms/public/blog/<slug>/ - AllowAny, single published post.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            post = BlogPost.objects.get(slug=slug, status=BlogPost.STATUS_PUBLISHED)
        except BlogPost.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BlogPostSerializer(post).data)