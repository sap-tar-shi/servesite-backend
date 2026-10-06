import secrets
from django.db import transaction
from django.utils.text import slugify
from .models import Tenant
from accounts.models import User, Membership


class SlugTaken(Exception):
    pass


@transaction.atomic
def provision_tenant(slug: str, name: str, owner_email: str, owner_password: str | None = None):
    """
    Creates a Tenant + its owner User + owner Membership. The tenant's
    SiteConfig is deliberately NOT created here - the owner picks their
    template from the admin (cms.provisioning.select_template).
    Shared by platform_admin.TenantListCreateView and accounts.SignupView.
    Returns (tenant, owner_user, owner_created, temp_password).
    """
    slug = slug.strip().lower()
    owner_email = owner_email.strip().lower()

    if Tenant.objects.filter(slug=slug).exists():
        raise SlugTaken(f"'{slug}' is already taken.")

    tenant = Tenant.objects.create(slug=slug, name=name, status=Tenant.STATUS_TRIAL)

    owner_user, owner_created = User.objects.get_or_create(email=owner_email)
    temp_password = None
    if owner_created:
        password_to_set = owner_password or secrets.token_urlsafe(12)
        owner_user.set_password(password_to_set)
        owner_user.save()
        if not owner_password:
            temp_password = password_to_set
    Membership.objects.get_or_create(user=owner_user, tenant=tenant, defaults={"role": Membership.ROLE_OWNER})

    return tenant, owner_user, owner_created, temp_password


def suggest_slugs(name: str, count: int = 5) -> list[str]:
    """Available slug variants derived from a restaurant name."""
    base = slugify(name)[:50] or "restaurant"
    candidates = [base]
    for suf in ["eats", "kitchen", "cafe", "co", "hq"]:
        candidates.append(f"{base}-{suf}")
    for n in range(2, 6):
        candidates.append(f"{base}-{n}")

    existing = set(Tenant.objects.filter(slug__in=candidates).values_list("slug", flat=True))
    return [c for c in candidates if c not in existing][:count]