from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from tenants.models import Tenant
from accounts.models import User, Membership
from .models import MediaAsset


class MediaUploadTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="media-tenant", name="Media Tenant")
        self.owner = User.objects.create_user(email="owner@media.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)
        self.client.post(
            "/api/auth/login/",
            {"email": "owner@media.com", "password": "testpass123"},
            content_type="application/json",
            HTTP_HOST="media-tenant.localhost",
        )

    @override_settings(
        STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}
    )
    @patch("cms.views.generate_thumbnail.delay")
    def test_upload_creates_media_asset_and_queues_thumbnail(self, mock_thumbnail_task):
        fake_image = SimpleUploadedFile("test.jpg", b"fake-image-bytes", content_type="image/jpeg")

        resp = self.client.post(
            "/api/cms/media/",
            {"file": fake_image},
            HTTP_HOST="media-tenant.localhost",
        )

        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.json())

        asset = MediaAsset.unscoped.get(id=resp.json()["id"])
        self.assertEqual(asset.tenant, self.tenant)
        mock_thumbnail_task.assert_called_once_with(str(asset.id))

    def test_upload_without_file_returns_400(self):
        resp = self.client.post("/api/cms/media/", {}, HTTP_HOST="media-tenant.localhost")
        self.assertEqual(resp.status_code, 400)