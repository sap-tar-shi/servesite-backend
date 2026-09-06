from django.test import TestCase
from tenants.models import Tenant
from .models import User


class CrossSubdomainSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="owner@example.com", password="testpass123")
        Tenant.objects.create(slug="tenant-a", name="Tenant A")
        Tenant.objects.create(slug="tenant-b", name="Tenant B")

    def test_login_then_me_works_on_different_subdomain(self):
        login_resp = self.client.post(
            "/api/auth/login/",
            {"email": "owner@example.com", "password": "testpass123"},
            content_type="application/json",
            HTTP_HOST="tenant-a.localhost",
        )
        self.assertEqual(login_resp.status_code, 200)

        me_resp = self.client.get("/api/auth/me/", HTTP_HOST="tenant-b.localhost")
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["email"], "owner@example.com")

    def test_unauthenticated_me_returns_401(self):
        resp = self.client.get("/api/auth/me/", HTTP_HOST="tenant-a.localhost")
        self.assertEqual(resp.status_code, 401)