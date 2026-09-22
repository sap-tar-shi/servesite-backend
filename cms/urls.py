from django.urls import path
from .views import (
    SiteContentUpdateView, EditableFieldsView, MediaUploadView, SiteContentView,
    AllSiteContentView, PublicSiteContentView, AvailableUpgradeView, TemplateUpgradeView,
    AvailableTemplatesView, TemplateSwitchView, BlogPostListCreateView, BlogPostDetailView,
    PublicBlogListView, PublicBlogDetailView,
)


urlpatterns = [
    path("site-content/", SiteContentUpdateView.as_view(), name="site-content-update"),
    path("site-content/get/", SiteContentView.as_view(), name="site-content-get"),
    path("site-content/all/", AllSiteContentView.as_view(), name="site-content-all"),
    path("public/site-content/", PublicSiteContentView.as_view(), name="public-site-content"),
    path("editable-fields/", EditableFieldsView.as_view(), name="editable-fields"),
    path("media/", MediaUploadView.as_view(), name="media-upload"),
    path("template/available-upgrade/", AvailableUpgradeView.as_view(), name="template-available-upgrade"),
    path("template/upgrade/", TemplateUpgradeView.as_view(), name="template-upgrade"),
    path("template/available-templates/", AvailableTemplatesView.as_view(), name="template-available-templates"),
    path("template/switch/", TemplateSwitchView.as_view(), name="template-switch"),
    path("blog/", BlogPostListCreateView.as_view(), name="blog-list-create"),
    path("blog/<uuid:post_id>/", BlogPostDetailView.as_view(), name="blog-detail"),
    path("public/blog/", PublicBlogListView.as_view(), name="public-blog-list"),
    path("public/blog/<slug:slug>/", PublicBlogDetailView.as_view(), name="public-blog-detail"),
]