from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from menu.pricing import price_cart_items, CartPricingError
from .models import Order, OrderItem
from .serializers import OrderSerializer


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

        order = Order.objects.create(tenant=request.tenant, subtotal=subtotal)
        for p in priced_items:
            OrderItem.objects.create(
                tenant=request.tenant,
                order=order,
                menu_item=p["menu_item"],
                item_name=p["menu_item"].name,
                unit_price=p["unit_price"],
                quantity=p["quantity"],
                line_total=p["line_total"],
                modifiers_snapshot=[{"id": str(m.id), "name": m.name, "price_delta": str(m.price_delta)} for m in p["modifiers"]],
            )

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(generics.RetrieveAPIView):
    """GET /api/orders/<id>/ - lets a diner poll their own order's status."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Order.objects.prefetch_related("items")