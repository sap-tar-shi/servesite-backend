from django.urls import path
from .views import widget_list_view

urlpatterns = [
    path("widgets/", widget_list_view, name="widget-list"),
]