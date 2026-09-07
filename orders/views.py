from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from menu.pricing import price_cart_items, CartPricingError
from .models import Order, OrderItem, OrderEvent
from .serializers import OrderSerializer
from tables.models import Table
from accounts.permissions import HasModulePermission


class OrderCreateView(APIView):
    """
    POST /api/orders/  - no auth (diners aren't logged in).
    Prices the cart using the exact same server-side logic as P2-T3's
    /cart/validate/, then persists it with a full price/name snapshot -
    nothing here is re-derived from MenuItem/Modifier after this point.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            priced_items, subtotal = price_cart_items(request.data.get("items"))
        except CartPricingError as e:
            return Response({"detail": e.detail}, status=status.HTTP_400_BAD_REQUEST)

        table_token = request.data.get("table_token")
        address = ""

        if table_token:
            try:
                table = Table.objects.get(table_token=table_token, is_active=True)
            except Table.DoesNotExist:
                return Response({"detail": "Invalid or inactive table QR code."}, status=status.HTTP_400_BAD_REQUEST)
            order_type = "dine_in"
        else:
            table = None
            order_type = request.data.get("order_type")
            if order_type not in ("takeaway", "online"):
                return Response(
                    {"detail": "order_type must be 'takeaway' or 'online' when no table QR code is scanned."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if order_type == "online":
                address = (request.data.get("address") or "").strip()
                if not address:
                    return Response({"detail": "address is required for online orders."}, status=status.HTTP_400_BAD_REQUEST)

        payment_mode = request.data.get("payment_mode")
        if payment_mode not in ("pay_now", "pay_at_counter"):
            return Response({"detail": "payment_mode must be 'pay_now' or 'pay_at_counter'."}, status=status.HTTP_400_BAD_REQUEST)
        if payment_mode == "pay_now" and not request.tenant.online_payment_enabled:
            return Response({"detail": "Pay now is not available for this restaurant."}, status=status.HTTP_400_BAD_REQUEST)
                    
        order = Order.objects.create(
            tenant=request.tenant, subtotal=subtotal, order_type=order_type, table=table, address=address,
        )
        OrderEvent.objects.create(tenant=request.tenant, order=order, from_status="", to_status="placed", actor=None)

        for p in priced_items:
            OrderItem.objects.create(
                tenant=request.tenant, order=order, menu_item=p["menu_item"], item_name=p["menu_item"].name,
                unit_price=p["unit_price"], quantity=p["quantity"], line_total=p["line_total"],
                modifiers_snapshot=[{"id": str(m.id), "name": m.name, "price_delta": str(m.price_delta)} for m in p["modifiers"]],
            )

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(generics.RetrieveAPIView):
    """GET /api/orders/<id>/ - lets a diner poll their own order's status."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Order.objects.prefetch_related("items")


class OrderTransitionView(APIView):
    """
    POST /api/orders/<id>/transition/  Body: {"to_status": "accepted"}
    Gated by the existing "live_orders" module (owner/manager/kitchen/
    waiter/staff per §12 - the same permission your P1-T11 throwaway
    LiveOrdersView proved out).
    """

    permission_classes = [HasModulePermission("live_orders")]

    def post(self, request, pk):
        order = Order.objects.get(pk=pk)
        new_status = request.data.get("to_status")
        try:
            order.transition_to(new_status, actor=request.user)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data)