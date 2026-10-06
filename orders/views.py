from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from menu.pricing import price_cart_items, CartPricingError
from .models import Order, OrderItem, OrderEvent
from .serializers import OrderSerializer
from tables.models import Table
from accounts.permissions import HasModulePermission
from django.core.cache import cache
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from core.permissions import TenantNotSuspended
import zoneinfo
from datetime import datetime, time, timedelta
from django.conf import settings
from django.db.models import Count, Q, Sum
from django.db.models.functions import ExtractHour, TruncDate
from accounts.models import Membership
from accounts.permissions import get_membership_for_request


class OrderCreateView(APIView):
    """
    POST /api/orders/  - no auth (diners aren't logged in).
    Prices the cart using the exact same server-side logic as P2-T3's
    /cart/validate/, then persists it with a full price/name snapshot -
    nothing here is re-derived from MenuItem/Modifier after this point.
    """

    permission_classes = [permissions.AllowAny, TenantNotSuspended]

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
            tenant=request.tenant, subtotal=subtotal, order_type=order_type, table=table,
            address=address, payment_mode=payment_mode,
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
    permission_classes = [permissions.AllowAny, TenantNotSuspended]

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


class LiveOrdersView(APIView):
    """
    GET /api/orders/live/?since=<ISO8601 timestamp>
    Per P2-T11 AC: returns only orders changed since the cursor, backed by
    the (tenant, updated_at) index. Cached for a short window (2s) since
    KDS/waiter clients poll every 3-5s and frequently overlap on the same
    (tenant, since) pair - this avoids re-hitting the DB for every client's
    near-identical poll.
    """

    permission_classes = [HasModulePermission("live_orders")]

    def get(self, request):
        since_param = request.query_params.get("since")
        since = parse_datetime(since_param) if since_param else None
        if since_param and since is None:
            return Response({"detail": "Invalid 'since' timestamp - use ISO 8601."}, status=status.HTTP_400_BAD_REQUEST)
        if since is None:
            since = timezone.now() - timezone.timedelta(hours=24)  # sane default: don't return all-time history on first poll

        cache_key = f"live_orders:{request.tenant.id}:{since.isoformat()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        orders = Order.objects.filter(updated_at__gt=since).prefetch_related("items").order_by("updated_at")
        data = OrderSerializer(orders, many=True).data
        cache.set(cache_key, data, timeout=2)
        return Response(data)
        
LIVE_STATUSES = ["placed", "accepted", "preparing", "ready"]
EXCLUDED_STATUSES = ["cancelled", "refunded"]  # never counted as orders
REVENUE_STATUSES = ["paid", "completed"]
RANGE_DAYS = {"today": 1, "7d": 7, "30d": 30}


def _mix(qs, field):
    rows = qs.order_by().values(field).annotate(count=Count("id")).order_by("-count")
    return [{"key": r[field], "count": r["count"]} for r in rows]


def _bucket_series(qs, tz, start, days):
    revenue = Sum("subtotal", filter=Q(status__in=REVENUE_STATUSES))
    if days == 1:
        rows = qs.annotate(b=ExtractHour("created_at", tzinfo=tz)).order_by().values("b").annotate(orders=Count("id"), revenue=revenue)
        keys = list(range(24))
        label = lambda k: f"{k:02d}:00"
    else:
        rows = qs.annotate(b=TruncDate("created_at", tzinfo=tz)).order_by().values("b").annotate(orders=Count("id"), revenue=revenue)
        keys = [(start + timedelta(days=i)).date() for i in range(days)]
        label = lambda k: k.isoformat()
    by_key = {r["b"]: r for r in rows}
    out = []
    for k in keys:
        r = by_key.get(k)
        out.append({
            "label": label(k),
            "orders": r["orders"] if r else 0,
            "revenue": float(r["revenue"] or 0) if r else 0.0,
        })
    return out


class OrderStatsView(APIView):
    """
    GET /api/orders/stats/?range=today|7d|30d

    One call for the whole admin Overview. Money fields (revenue, average
    order value, daily series, top items) are returned ONLY to owner/manager
    - kitchen/waiter/staff get order counts + live count for today and
    nothing else, enforced here (not just hidden in the UI).
    """

    permission_classes = [HasModulePermission("live_orders")]

    def get(self, request):
        membership = get_membership_for_request(request)
        can_see_money = membership.role in (Membership.ROLE_OWNER, Membership.ROLE_MANAGER)

        range_key = request.query_params.get("range", "today")
        if range_key not in RANGE_DAYS:
            return Response({"detail": "range must be one of: today, 7d, 30d."}, status=status.HTTP_400_BAD_REQUEST)
        if not can_see_money:
            range_key = "today"

        tz = zoneinfo.ZoneInfo(getattr(settings, "STATS_TIME_ZONE", settings.TIME_ZONE))
        days = RANGE_DAYS[range_key]
        today_start = datetime.combine(timezone.now().astimezone(tz).date(), time.min, tzinfo=tz)
        start = today_start - timedelta(days=days - 1)
        end = today_start + timedelta(days=1)
        prev_start = start - timedelta(days=days)

        counted = Order.objects.exclude(status__in=EXCLUDED_STATUSES)
        current = counted.filter(created_at__gte=start, created_at__lt=end)
        previous = counted.filter(created_at__gte=prev_start, created_at__lt=start)

        data = {
            "range": range_key,
            "days": days,
            "timezone": str(tz),
            "can_see_money": can_see_money,
            "live_count": Order.objects.filter(status__in=LIVE_STATUSES).count(),
            "orders": {"current": current.count(), "previous": previous.count()},
            "order_mix": _mix(current, "order_type"),
            "payment_mix": _mix(current, "payment_mode"),
            "revenue": None,
            "average_order_value": None,
            "series": None,
            "top_items": None,
        }

        if can_see_money:
            paid_cur = current.filter(status__in=REVENUE_STATUSES)
            paid_prev = previous.filter(status__in=REVENUE_STATUSES)
            rev_cur = paid_cur.aggregate(t=Sum("subtotal"))["t"] or 0
            rev_prev = paid_prev.aggregate(t=Sum("subtotal"))["t"] or 0
            paid_count = paid_cur.count()

            data["revenue"] = {"current": float(rev_cur), "previous": float(rev_prev)}
            data["average_order_value"] = round(float(rev_cur) / paid_count, 2) if paid_count else 0.0
            data["series"] = _bucket_series(current, tz, start, days)

            top = (
                OrderItem.objects.filter(order__created_at__gte=start, order__created_at__lt=end)
                .exclude(order__status__in=EXCLUDED_STATUSES)
                .values("item_name")
                .annotate(qty=Sum("quantity"), total=Sum("line_total"))
                .order_by("-qty")[:5]
            )
            data["top_items"] = [
                {"item_name": t["item_name"], "quantity": t["qty"], "revenue": float(t["total"] or 0)} for t in top
            ]

        return Response(data)