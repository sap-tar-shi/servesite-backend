import uuid
from django.db import models
from django.core.exceptions import ValidationError


def validate_capability_manifest(value):
    """
    Minimal structural validation for the capability manifest JSON.
    Full JSON-Schema validation can be added later (P4-T1+ when a second
    template arrives and cross-template consistency starts to matter);
    for now this guards the shape every downstream consumer (CMS, admin
    edit-field resolution in P1-T17) depends on.
    """
    if not isinstance(value, dict):
        raise ValidationError("Manifest must be a JSON object")

    required_keys = {"sections", "editable_fields", "theme_tokens"}
    missing = required_keys - value.keys()
    if missing:
        raise ValidationError(f"Manifest missing required keys: {missing}")

    if not isinstance(value["sections"], list):
        raise ValidationError("Manifest 'sections' must be a list")
    if not isinstance(value["editable_fields"], list):
        raise ValidationError("Manifest 'editable_fields' must be a list")
    if not isinstance(value["theme_tokens"], list):
        raise ValidationError("Manifest 'theme_tokens' must be a list")


class TemplateRegistry(models.Model):
    """
    A template *family* (e.g. 'classic-bistro'). Not itself versioned —
    TemplateVersion below holds the actual pinned, immutable versions.
    """

    STATUS_ACTIVE = "active"
    STATUS_DEPRECATED = "deprecated"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_DEPRECATED, "Deprecated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150)
    preview_image = models.URLField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "templates_registry"

    def __str__(self):
        return self.display_name


class TemplateVersion(models.Model):
    """
    An immutable, pinned version of a template (e.g. classic-bistro@1.0.0).
    Per architecture §6: "Publishing A@2.0.0 never silently mutates live
    sites; owners opt into upgrades." Once published, a version's manifest
    should be treated as append-only in practice, though not DB-enforced
    here - discipline, not a hard constraint, since super-admin tooling
    (P3-T8) is the only writer.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(TemplateRegistry, on_delete=models.CASCADE, related_name="versions")
    version = models.CharField(max_length=20)  # semver string, e.g. "1.0.0"
    capability_manifest = models.JSONField(validators=[validate_capability_manifest])
    changelog = models.TextField(blank=True)
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "templates_registry_version"
        constraints = [
            models.UniqueConstraint(fields=["template", "version"], name="unique_template_version"),
        ]
        ordering = ["-published_at"]

    def __str__(self):
        return f"{self.template.name}@{self.version}"