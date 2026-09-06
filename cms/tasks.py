import io
from celery import shared_task
from PIL import Image
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