import logging
import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger("servesite.revalidation")


@shared_task
def revalidate_public_menu(tenant_slug):
    """
    Fires an on-demand ISR revalidation on the Next.js side for this
    tenant's public menu page (P1-T24). Best-effort: if the frontend is
    unreachable, we log and move on - the 60s timed revalidation from
    P1-T23 is the safety net, so a missed on-demand ping degrades to
    "content updates within 60s" rather than breaking anything.
    """
    try:
        requests.post(
            f"{settings.NEXT_APP_URL}/api/revalidate",
            json={"tag": f"menu-{tenant_slug}"},
            headers={"x-revalidate-secret": settings.REVALIDATE_SECRET},
            timeout=5,
        )
    except requests.RequestException:
        logger.warning("REVALIDATION_PING_FAILED tenant_slug=%s", tenant_slug)