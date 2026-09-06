from django.core.management.base import BaseCommand
from templates_registry.models import TemplateRegistry, TemplateVersion

# The manifest for our first template (P1-T16 will build the actual React
# package implementing this exact contract - landing + menu + contact).
CLASSIC_BISTRO_MANIFEST = {
    "sections": ["hero", "about", "menu", "gallery", "contact"],
    "editable_fields": [
        "restaurant_name",
        "tagline",
        "about_text",
        "hero_image",
        "logo",
        "address",
        "phone",
        "opening_hours",
    ],
    "theme_tokens": ["primary_color", "accent_color", "font_pairing"],
}


class Command(BaseCommand):
    help = "Seed the first template (classic-bistro) at version 1.0.0"

    def handle(self, *args, **options):
        template, created = TemplateRegistry.objects.get_or_create(
            name="classic-bistro",
            defaults={"display_name": "Classic Bistro"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created template: {template}"))
        else:
            self.stdout.write(self.style.WARNING(f"Template already exists: {template}"))

        version, created = TemplateVersion.objects.get_or_create(
            template=template,
            version="1.0.0",
            defaults={
                "capability_manifest": CLASSIC_BISTRO_MANIFEST,
                "changelog": "Initial release: hero, about, menu, gallery, contact sections.",
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created version: {version}"))
        else:
            self.stdout.write(self.style.WARNING(f"Version already exists: {version}"))