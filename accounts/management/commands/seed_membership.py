from django.core.management.base import BaseCommand
from tenants.models import Tenant
from accounts.models import User, Membership


class Command(BaseCommand):
    help = "Seed a membership linking a user to a tenant with a role"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--role", default=Membership.ROLE_OWNER, choices=[c[0] for c in Membership.ROLE_CHOICES])

    def handle(self, *args, **options):
        user = User.objects.get(email=options["email"])
        tenant = Tenant.objects.get(slug=options["slug"])
        membership, created = Membership.objects.get_or_create(
            user=user, tenant=tenant, defaults={"role": options["role"]}
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created membership: {membership}"))
        else:
            self.stdout.write(self.style.WARNING(f"Membership already exists: {membership}"))