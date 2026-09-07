import io
import qrcode
from django.http import HttpResponse
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.permissions import HasModulePermission
from .models import Table
from .serializers import TableSerializer


class TableListCreateView(generics.ListCreateAPIView):
    serializer_class = TableSerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return Table.objects.all()

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class TableDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TableSerializer
    permission_classes = [HasModulePermission("menu_management")]

    def get_queryset(self):
        return Table.objects.all()


class TableRotateTokenView(APIView):
    """POST /api/tables/<id>/rotate-token/ - invalidates the existing QR."""

    permission_classes = [HasModulePermission("menu_management")]

    def post(self, request, pk):
        table = Table.objects.get(pk=pk)  # tenant-scoped manager - 404s for other tenants' ids
        table.rotate_token()
        return Response(TableSerializer(table).data)


class TableQRView(APIView):
    """
    GET /api/tables/<id>/qr/ - returns a PNG QR code encoding this table's
    ordering URL. The target URL isn't a real ordering page yet (that's
    P2-T3/T5) - the QR just needs a stable, correct format today; scanning
    it before then will 404, which is expected at this stage of the plan.
    """

    permission_classes = [HasModulePermission("menu_management")]

    def get(self, request, pk):
        table = Table.objects.get(pk=pk)
        order_url = f"http://{request.tenant.slug}.localhost:3000/order?table={table.table_token}"

        img = qrcode.make(order_url)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return HttpResponse(buffer.getvalue(), content_type="image/png")