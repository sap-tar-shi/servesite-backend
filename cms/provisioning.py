from django.db import transaction

from core.db import set_tenant_guc
from templates_registry.management.commands.seed_template import TEMPLATES
from templates_registry.models import TemplateRegistry, TemplateVersion
from tenants.context import get_current_tenant, reset_current_tenant, set_current_tenant

from .models import Page, Section, SiteConfig


def ensure_templates():
    """Idempotently registers the platform's template families + versions,
    so a fresh database never needs a manual seed_template run."""
    for name, display_name, version_str, manifest, changelog in TEMPLATES:
        template, _ = TemplateRegistry.objects.get_or_create(
            name=name, defaults={"display_name": display_name}
        )
        TemplateVersion.objects.get_or_create(
            template=template,
            version=version_str,
            defaults={"capability_manifest": manifest, "changelog": changelog},
        )


def select_template(tenant, family):
    """
    The moment a tenant's slug gets connected to a template. Pins the
    tenant's SiteConfig to the LATEST version of `family`, creating the
    SiteConfig (+ landing/menu pages + hero/about/contact sections) on the
    first choice, or re-pinning on later choices/upgrades. Existing content
    is never touched. Caller must ensure `family` has at least one version.
    """
    version = family.versions.order_by("-sequence").first()

    previous = get_current_tenant()
    token = set_current_tenant(tenant)
    set_tenant_guc(tenant.id)
    try:
        with transaction.atomic():
            site_config, created = SiteConfig.objects.get_or_create(
                tenant=tenant,
                defaults={"template_version": version, "status": SiteConfig.STATUS_DRAFT},
            )
            if not created and site_config.template_version_id != version.id:
                site_config.template_version = version
                site_config.save(update_fields=["template_version"])

            landing, _ = Page.objects.get_or_create(
                tenant=tenant, page_type=Page.TYPE_LANDING, defaults={"enabled": True}
            )
            Page.objects.get_or_create(
                tenant=tenant, page_type=Page.TYPE_MENU, defaults={"enabled": True}
            )
            for section_type, position, content in [
                ("hero", 0, {"restaurant_name": tenant.name, "headline": f"Welcome to {tenant.name}"}),
                ("about", 1, {}),
                ("contact", 2, {}),
            ]:
                Section.objects.get_or_create(
                    tenant=tenant, page=landing, section_type=section_type,
                    defaults={"ordered_position": position, "content": content},
                )
        return site_config
    finally:
        reset_current_tenant(token)
        set_tenant_guc(previous.id if previous else None)