from django.urls import path
from .views import TableListCreateView, TableDetailView, TableRotateTokenView, TableQRView

urlpatterns = [
    path("", TableListCreateView.as_view(), name="table-list-create"),
    path("<uuid:pk>/", TableDetailView.as_view(), name="table-detail"),
    path("<uuid:pk>/rotate-token/", TableRotateTokenView.as_view(), name="table-rotate-token"),
    path("<uuid:pk>/qr/", TableQRView.as_view(), name="table-qr"),
]