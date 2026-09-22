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

# P4-T1: second template. Sections + editable_fields are DELIBERATELY
# identical to CLASSIC_BISTRO_MANIFEST - per architecture §6, content is
# stored independent of template, so an identical section contract is what
# lets an owner switch templates later (P4-T3) with zero content migration.
# Only theme_tokens differs in spirit (same token names, wider font_pairing
# choice - see templates/shared/types.ts on the frontend).
GARDEN_TERRACE_MANIFEST = {
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

TEMPLATES = [
    (
        "classic-bistro",
        "Classic Bistro",
        "1.0.0",
        CLASSIC_BISTRO_MANIFEST,
        "Initial release: hero, about, menu, gallery, contact sections.",
    ),
    (
        "garden-terrace",
        "Garden Terrace",
        "1.0.0",
        GARDEN_TERRACE_MANIFEST,
        "Initial release: lighter/airier layout, same section contract as classic-bistro (P4-T1).",
    ),
]


class Command(BaseCommand):
    help = "Seed the platform's templates (classic-bistro, garden-terrace) at their initial versions"

    def handle(self, *args, **options):
        for name, display_name, version_str, manifest, changelog in TEMPLATES:
            template, created = TemplateRegistry.objects.get_or_create(
                name=name,
                defaults={"display_name": display_name},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created template: {template}"))
            else:
                self.stdout.write(self.style.WARNING(f"Template already exists: {template}"))

            version, created = TemplateVersion.objects.get_or_create(
                template=template,
                version=version_str,
                defaults={
                    "capability_manifest": manifest,
                    "changelog": changelog,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created version: {version}"))
            else:
                self.stdout.write(self.style.WARNING(f"Version already exists: {version}"))