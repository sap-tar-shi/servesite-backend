class NonWhitelistedFieldError(Exception):
    """Raised when a caller attempts to write a field not declared editable
    in the tenant's pinned TemplateVersion manifest."""

    def __init__(self, rejected_fields):
        self.rejected_fields = rejected_fields
        super().__init__(f"Fields not whitelisted for editing: {rejected_fields}")


def get_editable_fields(site_config):
    """Returns the set of field names this tenant's pinned template version
    allows an owner to edit, per its capability_manifest."""
    return set(site_config.template_version.capability_manifest.get("editable_fields", []))


def filter_to_whitelisted_fields(site_config, requested_fields: dict):
    """
    Splits requested_fields into (allowed, rejected) against the manifest.
    Raises NonWhitelistedFieldError if ANY requested field is not whitelisted -
    fail closed, not a silent partial-apply, so a caller always knows
    exactly what happened rather than guessing which fields "stuck."
    """
    allowed_fields = get_editable_fields(site_config)
    requested_keys = set(requested_fields.keys())
    rejected = requested_keys - allowed_fields

    if rejected:
        raise NonWhitelistedFieldError(rejected)

    return requested_fields