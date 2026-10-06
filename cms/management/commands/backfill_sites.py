from django.core.management.base import BaseCommand
from tenants.models import Tenant
from cms.provisioning import provision_site


class Command(BaseCommand):
    help = "Give every existing tenant a SiteConfig + landing/menu pages + hero/about/contact sections (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--slug", help="Only this tenant (default: all)")

    def handle(self, *args, **options):
        tenants = Tenant.objects.all()
        if options["slug"]:
            tenants = tenants.filter(slug=options["slug"])
        for tenant in tenants:
            provision_site(tenant)
            self.stdout.write(self.style.SUCCESS(f"Provisioned site for {tenant.slug}"))