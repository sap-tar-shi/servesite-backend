from django.urls import path
from .views import SiteContentUpdateView, EditableFieldsView, MediaUploadView, SiteContentView, AllSiteContentView

urlpatterns = [
    path("site-content/", SiteContentUpdateView.as_view(), name="site-content-update"),
    path("site-content/get/", SiteContentView.as_view(), name="site-content-get"),
    path("site-content/all/", AllSiteContentView.as_view(), name="site-content-all"),
    path("editable-fields/", EditableFieldsView.as_view(), name="editable-fields"),
    path("media/", MediaUploadView.as_view(), name="media-upload"),
]