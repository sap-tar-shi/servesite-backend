from django.test import TestCase
from django.db import transaction
from tenants.models import Tenant
from tenants.context import set_current_tenant, reset_current_tenant
from core.db import set_tenant_guc
from templates_registry.models import TemplateRegistry, TemplateVersion
from .models import SiteConfig, Page, Section


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