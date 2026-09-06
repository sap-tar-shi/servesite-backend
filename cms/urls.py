from django.urls import path
from .views import SiteContentUpdateView, EditableFieldsView

urlpatterns = [
    path("site-content/", SiteContentUpdateView.as_view(), name="site-content-update"),
    path("editable-fields/", EditableFieldsView.as_view(), name="editable-fields"),
]