from django.db import models
from core.models import TenantScopedModel
from templates_registry.models import TemplateVersion


class SiteConfig(TenantScopedModel):
    """
    One per tenant. Pins the tenant to a specific, immutable TemplateVersion
    (arch §6: "Live sites are pinned to a specific version"). Switching
    template_version is the only way an owner's site changes presentation -
    content underneath is untouched.
    """

    STATUS_DRAFT = "draft"
    STATUS_LIVE = "live"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_LIVE, "Live"),
    ]

    template_version = models.ForeignKey(TemplateVersion, on_delete=models.PROTECT)
    theme_config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    class Meta(TenantScopedModel.Meta):
        db_table = "cms_site_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="one_site_config_per_tenant"),
        ]

    def __str__(self):
        return f"SiteConfig({self.tenant.slug})"


class Page(TenantScopedModel):
    TYPE_LANDING = "landing"
    TYPE_MENU = "menu"
    TYPE_BLOG = "blog"
    TYPE_CONTACT = "contact"
    TYPE_CHOICES = [
        (TYPE_LANDING, "Landing"),
        (TYPE_MENU, "Menu"),
        (TYPE_BLOG, "Blog"),
        (TYPE_CONTACT, "Contact"),
    ]

    page_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    enabled = models.BooleanField(default=True)
    seo_meta = models.JSONField(default=dict, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "cms_page"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "page_type"], name="one_page_per_type_per_tenant"),
        ]

    def __str__(self):
        return f"{self.tenant.slug}/{self.page_type}"


class Section(TenantScopedModel):
    """
    A block of typed content within a Page (e.g. 'hero', 'about'). The
    `section_type` must correspond to an entry in the pinned TemplateVersion's
    manifest['sections'] - enforcement of that constraint happens at the
    admin/API layer (P1-T17), not the DB layer, since it depends on a JOIN
    through SiteConfig -> TemplateVersion that changes over time (template
    upgrades).
    """

    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="sections")
    section_type = models.CharField(max_length=50)
    ordered_position = models.PositiveIntegerField(default=0)
    content = models.JSONField(default=dict, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "cms_section"
        indexes = TenantScopedModel.Meta.indexes + [
            models.Index(fields=["tenant", "page", "ordered_position"]),
        ]
        ordering = ["ordered_position"]

    def __str__(self):
        return f"{self.page} / {self.section_type} (#{self.ordered_position})"


class MediaAsset(TenantScopedModel):
    """
    Metadata row for an uploaded media file. The actual bytes live in S3/CDN
    (P0-T7 storage backend) - this table never stores file content, only
    the storage key/URL, per arch §14 ("Django never serves user images").
    Async thumbnailing (P1-T18, via Celery) will populate thumbnail_url.
    """

    TYPE_IMAGE = "image"
    TYPE_CHOICES = [(TYPE_IMAGE, "Image")]

    storage_key = models.CharField(max_length=500)
    url = models.URLField()
    thumbnail_url = models.URLField(blank=True, null=True)
    media_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_IMAGE)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "cms_media_asset"

    def __str__(self):
        return f"{self.tenant.slug}/{self.storage_key}"