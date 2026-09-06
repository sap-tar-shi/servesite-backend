from django.core.management.base import BaseCommand
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Seed a demo tenant for local development"

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="demo-restaurant")
        parser.add_argument("--name", default="Demo Restaurant")

    def handle(self, *args, **options):
        tenant, created = Tenant.objects.get_or_create(
            slug=options["slug"],
            defaults={"name": options["name"], "status": Tenant.STATUS_TRIAL},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created tenant: {tenant}"))
        else:
            self.stdout.write(self.style.WARNING(f"Tenant already exists: {tenant}"))