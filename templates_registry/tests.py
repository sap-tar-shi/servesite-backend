from django.test import TestCase
from django.core.exceptions import ValidationError
from .models import TemplateRegistry, TemplateVersion, validate_capability_manifest


class TemplateManifestTests(TestCase):
    def setUp(self):
        self.template = TemplateRegistry.objects.create(
            name="test-template", display_name="Test Template"
        )

    def test_valid_manifest_is_accepted(self):
        version = TemplateVersion.objects.create(
            template=self.template,
            version="1.0.0",
            capability_manifest={
                "sections": ["hero", "menu"],
                "editable_fields": ["name"],
                "theme_tokens": ["primary_color"],
            },
        )
        version.full_clean()  # should not raise

    def test_manifest_missing_required_key_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_capability_manifest({"sections": ["hero"], "editable_fields": ["name"]})

    def test_manifest_wrong_type_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_capability_manifest("not-a-dict")

    def test_version_uniqueness_per_template(self):
        TemplateVersion.objects.create(
            template=self.template,
            version="1.0.0",
            capability_manifest={"sections": [], "editable_fields": [], "theme_tokens": []},
        )
        with self.assertRaises(Exception):
            TemplateVersion.objects.create(
                template=self.template,
                version="1.0.0",
                capability_manifest={"sections": [], "editable_fields": [], "theme_tokens": []},
            )

    def test_seeded_classic_bistro_template_exists(self):
        from django.core.management import call_command
        call_command("seed_template")
        template = TemplateRegistry.objects.get(name="classic-bistro")
        version = template.versions.get(version="1.0.0")
        self.assertIn("hero", version.capability_manifest["sections"])
        self.assertIn("restaurant_name", version.capability_manifest["editable_fields"])