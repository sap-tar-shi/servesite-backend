from django.core.management.base import BaseCommand
from billing.models import Plan


class Command(BaseCommand):
    help = "Seed the platform's default Plan rows (idempotent)."

    def handle(self, *args, **options):
        plans = [
            {
                "name": "Starter",
                "price": "999.00",
                "billing_interval": "monthly",
                "feature_limits": {
                    "template_count": 1,
                    "custom_domain_allowed": False,
                    "blog_allowed": False,
                    "max_menu_items": 50,
                    "max_staff_accounts": 3,
                },
            },
            {
                "name": "Growth",
                "price": "2499.00",
                "billing_interval": "monthly",
                "feature_limits": {
                    "template_count": 3,
                    "custom_domain_allowed": True,
                    "blog_allowed": True,
                    "max_menu_items": 200,
                    "max_staff_accounts": 10,
                },
            },
        ]
        for data in plans:
            plan, created = Plan.objects.update_or_create(
                name=data["name"], defaults=data
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} plan: {plan.name}"))