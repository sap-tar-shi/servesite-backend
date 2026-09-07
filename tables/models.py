import secrets
from django.db import models
from core.models import TenantScopedModel


def generate_table_token():
    # Unguessable per AC - 24 random bytes, URL-safe, no dictionary/sequence
    # pattern a diner could brute-force by guessing nearby table numbers.
    return secrets.token_urlsafe(24)


class Table(TenantScopedModel):
    label = models.CharField(max_length=100)
    table_token = models.CharField(max_length=64, unique=True, default=generate_table_token, editable=False)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "tables_table"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "label"], name="unique_table_label_per_tenant"),
        ]

    def rotate_token(self):
        """
        Per AC: token rotation invalidates old QR. The old token simply
        stops matching any Table row once overwritten - P2-T5's token->table
        resolution will look up Table.objects.get(table_token=...), so an
        old, printed QR silently 404s instead of resolving to this table.
        """
        self.table_token = generate_table_token()
        self.save(update_fields=["table_token"])

    def __str__(self):
        return f"{self.tenant.slug}/{self.label}"