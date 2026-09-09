import io
from celery import shared_task
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

THUMBNAIL_SIZE = (400, 400)


@shared_task
def generate_thumbnail(media_asset_id):
    """
    Async thumbnail generation, per architecture §14 ("image processing/
    thumbnailing" is explicitly a Celery responsibility - Django never
    serves user images directly, and the request/response cycle never
    blocks on image processing).
    """
    from .models import MediaAsset  # local import: avoids app-loading-order issues in Celery workers

    try:
        asset = MediaAsset.unscoped.get(id=media_asset_id)
    except MediaAsset.DoesNotExist:
        return

    with default_storage.open(asset.storage_key, "rb") as f:
        image = Image.open(f)
        image = image.convert("RGB")
        image.thumbnail(THUMBNAIL_SIZE)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        buffer.seek(0)

        thumb_key = f"thumbnails/{asset.storage_key}"
        saved_path = default_storage.save(thumb_key, ContentFile(buffer.read()))
        asset.thumbnail_url = default_storage.url(saved_path)
        asset.save(update_fields=["thumbnail_url"])


@shared_task
def revalidate_public_site(tenant_slug):
    """Same pattern as menu.tasks.revalidate_public_menu - best-effort ping,
    60s timed revalidation from P1-T23 is the safety net if this fails."""
    import requests
    import logging
    logger = logging.getLogger("servesite.revalidation")
    try:
        requests.post(
            f"{settings.NEXT_APP_URL}/api/revalidate",
            json={"tag": f"site-{tenant_slug}"},
            headers={"x-revalidate-secret": settings.REVALIDATE_SECRET},
            timeout=5,
        )
    except requests.RequestException:
        logger.warning("REVALIDATION_PING_FAILED tenant_slug=%s", tenant_slug)