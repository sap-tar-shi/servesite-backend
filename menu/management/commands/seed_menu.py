from django.core.management.base import BaseCommand
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from menu.models import MenuCategory, MenuItem


class Command(BaseCommand):
    help = "Seed a demo menu (categories + items) for a tenant"

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="demo-restaurant")

    def handle(self, *args, **options):
        tenant = Tenant.objects.get(slug=options["slug"])
        token = set_current_tenant(tenant)
        set_tenant_guc(tenant.id)
        try:
            starters, _ = MenuCategory.objects.get_or_create(
                tenant=tenant, name="Starters", defaults={"ordered_position": 0})
            mains, _ = MenuCategory.objects.get_or_create(
                tenant=tenant, name="Mains", defaults={"ordered_position": 1})

            MenuItem.objects.get_or_create(tenant=tenant, category=starters, name="Garlic Bread",
                defaults={"description": "Toasted with herb butter.", "price": "149.00", "ordered_position": 0})
            MenuItem.objects.get_or_create(tenant=tenant, category=starters, name="Soup of the Day",
                defaults={"description": "Ask your server.", "price": "179.00", "ordered_position": 1})
            MenuItem.objects.get_or_create(tenant=tenant, category=mains, name="Margherita Pizza",
                defaults={"description": "San Marzano tomato, fior di latte, basil.", "price": "449.00", "ordered_position": 0})
            MenuItem.objects.get_or_create(tenant=tenant, category=mains, name="Grilled Paneer Steak",
                defaults={"description": "Charred paneer, chimichurri, roast veg.", "price": "399.00", "ordered_position": 1})

            self.stdout.write(self.style.SUCCESS(f"Seeded menu for {tenant.slug}"))
        finally:
            reset_current_tenant(token)
            set_tenant_guc(None)