from django.core.management.base import BaseCommand
from platform_admin.models import SuperAdmin


class Command(BaseCommand):
    help = "Create a SuperAdmin for platform-admin origin testing."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        admin, created = SuperAdmin.objects.get_or_create(email=options["email"].lower())
        admin.set_password(options["password"])
        admin.save()
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} superadmin: {admin.email}"))