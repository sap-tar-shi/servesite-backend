import secrets

from django.db.models.signals import post_save
from django.dispatch import receiver

from tenants.models import Tenant
from .models import User, Membership


def shared_staff_email(slug):
    """
    Deterministic, per-tenant, globally-unique email for the
    auto-provisioned shared staff login. Not a real inbox - never used
    for notifications.
    """
    return f"staff@{slug}.staff.internal"


def provision_shared_staff_account(tenant):
    """
    Idempotent: creates the shared staff User + Membership if not already
    present. Password is never known even at creation time except via
    StaffCredentialsView.regenerate - callers should treat the initial
    password as unusable until the owner explicitly reveals/regenerates it.
    """
    email = shared_staff_email(tenant.slug)
    user, user_created = User.objects.get_or_create(email=email)
    if user_created:
        user.set_password(secrets.token_urlsafe(16))
        user.save()

    membership, _ = Membership.objects.get_or_create(
        user=user, tenant=tenant,
        defaults={"role": Membership.ROLE_STAFF, "is_shared_account": True},
    )
    return membership


@receiver(post_save, sender=Tenant)
def auto_provision_shared_staff_on_tenant_creation(sender, instance, created, **kwargs):
    if created:
        provision_shared_staff_account(instance)