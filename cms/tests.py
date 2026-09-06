from django.test import TestCase
from django.db import transaction
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from templates_registry.models import TemplateRegistry, TemplateVersion
from .models import SiteConfig, Page, Section
from accounts.models import User, Membership


class CMSContentIsolationTests(TestCase):
    def setUp(self):
        self.template = TemplateRegistry.objects.create(name="t1", display_name="T1")
        self.version = TemplateVersion.objects.create(
            template=self.template,
            version="1.0.0",
            capability_manifest={"sections": ["hero"], "editable_fields": [], "theme_tokens": []},
        )
        self.tenant_a = Tenant.objects.create(slug="cms-a", name="CMS A")
        self.tenant_b = Tenant.objects.create(slug="cms-b", name="CMS B")

        self._seed_page(self.tenant_a, "A's secret headline")
        self._seed_page(self.tenant_b, "B's secret headline")

    def _seed_page(self, tenant, headline):
        token = set_current_tenant(tenant)
        set_tenant_guc(tenant.id)
        SiteConfig.objects.create(tenant=tenant, template_version=self.version)
        page = Page.objects.create(tenant=tenant, page_type=Page.TYPE_LANDING)
        Section.objects.create(
            tenant=tenant, page=page, section_type="hero",
            content={"headline": headline},
        )
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_content_is_isolated_per_tenant(self):
        token = set_current_tenant(self.tenant_a)
        set_tenant_guc(self.tenant_a.id)
        sections = list(Section.objects.all())
        reset_current_tenant(token)
        set_tenant_guc(None)

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].content["headline"], "A's secret headline")

    def test_one_site_config_per_tenant_enforced(self):
        token = set_current_tenant(self.tenant_a)
        set_tenant_guc(self.tenant_a.id)
        with self.assertRaises(Exception):
            with transaction.atomic():
                SiteConfig.objects.create(tenant=self.tenant_a, template_version=self.version)
        reset_current_tenant(token)
        set_tenant_guc(None)

    def test_content_queryable_independent_of_template(self):
        """
        Proves arch §6: content is portable/queryable on its own, not
        entangled with template code - Section.content is plain JSON,
        readable without any template-rendering logic involved.
        """
        token = set_current_tenant(self.tenant_a)
        set_tenant_guc(self.tenant_a.id)
        section = Section.objects.get(section_type="hero")
        reset_current_tenant(token)
        set_tenant_guc(None)

        self.assertIsInstance(section.content, dict)
        self.assertIn("headline", section.content)


class WhitelistedEditFieldTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="edit-tenant", name="Edit Tenant")

        self.template = TemplateRegistry.objects.create(name="edit-template", display_name="Edit Template")
        self.version = TemplateVersion.objects.create(
            template=self.template,
            version="1.0.0",
            capability_manifest={
                "sections": ["hero"],
                "editable_fields": ["headline", "tagline"],
                "theme_tokens": [],
            },
        )

        self.owner = User.objects.create_user(email="owner@edit.com", password="testpass123")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.ROLE_OWNER)

        token = set_current_tenant(self.tenant)
        set_tenant_guc(self.tenant.id)
        SiteConfig.objects.create(tenant=self.tenant, template_version=self.version)
        page = Page.objects.create(tenant=self.tenant, page_type=Page.TYPE_LANDING)
        Section.objects.create(tenant=self.tenant, page=page, section_type="hero", content={})
        reset_current_tenant(token)
        set_tenant_guc(None)

    def _login(self):
        return self.client.post(
            "/api/auth/login/",
            {"email": "owner@edit.com", "password": "testpass123"},
            content_type="application/json",
            HTTP_HOST="edit-tenant.localhost",
        )

    def test_whitelisted_field_update_succeeds(self):
        self._login()
        resp = self.client.patch(
            "/api/cms/site-content/",
            {"section_type": "hero", "fields": {"headline": "New Headline"}},
            content_type="application/json",
            HTTP_HOST="edit-tenant.localhost",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["content"]["headline"], "New Headline")

    def test_non_whitelisted_field_rejected_with_403(self):
        self._login()
        resp = self.client.patch(
            "/api/cms/site-content/",
            {"section_type": "hero", "fields": {"secret_internal_field": "hacked"}},
            content_type="application/json",
            HTTP_HOST="edit-tenant.localhost",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("secret_internal_field", resp.json()["rejected_fields"])

    def test_mixed_whitelisted_and_non_whitelisted_rejects_entire_request(self):
        self._login()
        resp = self.client.patch(
            "/api/cms/site-content/",
            {"section_type": "hero", "fields": {"headline": "OK", "not_allowed": "nope"}},
            content_type="application/json",
            HTTP_HOST="edit-tenant.localhost",
        )
        self.assertEqual(resp.status_code, 403)

    def test_editable_fields_endpoint_returns_manifest_fields(self):
        self._login()
        resp = self.client.get("/api/cms/editable-fields/", HTTP_HOST="edit-tenant.localhost")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.json()["editable_fields"]), {"headline", "tagline"})