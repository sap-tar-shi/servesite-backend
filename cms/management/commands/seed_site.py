from django.core.management.base import BaseCommand
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from templates_registry.models import TemplateVersion
from cms.models import SiteConfig, Page, Section


class Command(BaseCommand):
    help = "Seed a full SiteConfig + Pages + Sections for a tenant"

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="demo-restaurant")

    def handle(self, *args, **options):
        tenant = Tenant.objects.get(slug=options["slug"])
        template_version = TemplateVersion.objects.get(
            template__name="classic-bistro", version="1.0.0"
        )

        token = set_current_tenant(tenant)
        set_tenant_guc(tenant.id)
        try:
            site_config, _ = SiteConfig.objects.get_or_create(
                tenant=tenant,
                defaults={"template_version": template_version, "status": SiteConfig.STATUS_LIVE},
            )

            landing, _ = Page.objects.get_or_create(
                tenant=tenant, page_type=Page.TYPE_LANDING, defaults={"enabled": True}
            )
            Section.objects.get_or_create(
                tenant=tenant, page=landing, section_type="hero", ordered_position=0,
                defaults={"content": {"headline": f"Welcome to {tenant.name}"}},
            )
            Section.objects.get_or_create(
                tenant=tenant, page=landing, section_type="about", ordered_position=1,
                defaults={"content": {"text": "A great place to eat."}},
            )

            menu_page, _ = Page.objects.get_or_create(
                tenant=tenant, page_type=Page.TYPE_MENU, defaults={"enabled": True}
            )

            self.stdout.write(self.style.SUCCESS(f"Seeded site for {tenant.slug}"))
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)