"""ReportService — authoritative financial and operational aggregation.

Revenue is counted ONCE per successful payment (Payment.verified_at window).
Pending/failed payments never count as revenue. Refunds are subtracted in
"net" figures explicitly, never double-counted.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.models import Payment
from apps.refunds.models import Refund

MONEY = DecimalField(max_digits=16, decimal_places=2)

RANGE_DAYS = {"today": 0, "yesterday": 1, "week": 7, "month": 30, "last_month": 60}


def resolve_range(range_key="month", date_from=None, date_to=None):
    """Return (start_dt, end_dt) — timezone-aware datetimes."""
    now = timezone.localtime(timezone.now())
    if range_key == "custom" and (date_from or date_to):
        try:
            start = timezone.datetime.fromisoformat(date_from) if date_from else (now - timedelta(days=30))
            end = timezone.datetime.fromisoformat(date_to) if date_to else now
        except ValueError:
            from apps.core.exceptions import ServiceError
            raise ServiceError("Dates must use the YYYY-MM-DD format.", code="invalid_date")
        if end < start:
            start, end = end, start
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        if timezone.is_naive(end):
            end = timezone.make_aware(end)
        return start, end + timedelta(days=1) if (end.hour, end.minute) == (0, 0) else end
    if range_key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if range_key == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if range_key == "last_month":
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return first_this - timedelta(days=30), first_this
    days = RANGE_DAYS.get(range_key, 30)
    return now - timedelta(days=days), now


class ReportService:
    @staticmethod
    def financial_summary(start, end):
        paid_payments = Payment.objects.filter(status__in=[Payment.Status.SUCCESSFUL,
                                                           Payment.Status.PARTIALLY_REFUNDED,
                                                           Payment.Status.REFUNDED],
                                               verified_at__gte=start, verified_at__lt=end)
        revenue = paid_payments.aggregate(t=Coalesce(Sum("amount"), Decimal("0"), output_field=MONEY))["t"]
        refunds = Refund.objects.filter(status=Refund.Status.SUCCESSFUL, processed_at__gte=start, processed_at__lt=end) \
            .aggregate(t=Coalesce(Sum("approved_amount"), Decimal("0"), output_field=MONEY))["t"]
        orders = Order.objects.filter(placed_at__gte=start, placed_at__lt=end)
        paid_orders = Order.objects.filter(payment_status__in=["paid", "partially_refunded", "refunded"],
                                           paid_at__gte=start, paid_at__lt=end)
        order_agg = paid_orders.aggregate(
            discounts=Coalesce(Sum("discount_amount"), Decimal("0"), output_field=MONEY),
            shipping=Coalesce(Sum("shipping_fee"), Decimal("0"), output_field=MONEY),
            subtotal=Coalesce(Sum("subtotal_amount"), Decimal("0"), output_field=MONEY))
        paid_count = paid_orders.count()

        def q(value):
            return Decimal(value or 0).quantize(Decimal("0.01"))
        return {
            "gross_sales": str(q(order_agg["subtotal"])),
            "collected_revenue": str(q(revenue)),
            "net_sales": str(q(revenue) - q(refunds)),
            "refunds": str(q(refunds)),
            "discounts_given": str(q(order_agg["discounts"])),
            "shipping_revenue": str(q(order_agg["shipping"])),
            "orders_created": orders.count(),
            "orders_paid": paid_count,
            "orders_cancelled": orders.filter(status__in=["cancelled", "expired"]).count(),
            "orders_awaiting_payment": orders.filter(status="pending_payment").count(),
            "payments_pending": Payment.objects.filter(status=Payment.Status.PENDING, created_at__gte=start, created_at__lt=end).count(),
            "payments_failed": Payment.objects.filter(status=Payment.Status.FAILED, created_at__gte=start, created_at__lt=end).count(),
            "average_order_value": str((q(revenue) / paid_count).quantize(Decimal("0.01"))) if paid_count else "0.00",
            "currency": "NGN",
        }

    @staticmethod
    def sales_by_day(start, end):
        rows = Payment.objects.filter(status=Payment.Status.SUCCESSFUL, verified_at__gte=start, verified_at__lt=end) \
            .annotate(day=TruncDate("verified_at")).values("day") \
            .annotate(revenue=Coalesce(Sum("amount"), Decimal("0"), output_field=MONEY), payments=Count("id")) \
            .order_by("day")
        return [{"date": r["day"].isoformat(), "revenue": str(r["revenue"]), "payments": r["payments"]} for r in rows]

    @staticmethod
    def sales_by_category(start, end, limit=50):
        rows = Order.objects.filter(payment_status__in=["paid", "partially_refunded", "refunded"],
                                    paid_at__gte=start, paid_at__lt=end) \
            .values("items__product__category__name") \
            .annotate(revenue=Coalesce(Sum("items__line_total"), Decimal("0"), output_field=MONEY),
                      units=Coalesce(Sum("items__quantity"), 0, output_field=DecimalField(max_digits=16, decimal_places=0))) \
            .order_by("-revenue")[:limit]
        return [{"category": r["items__product__category__name"], "revenue": str(r["revenue"]), "units": int(r["units"] or 0)} for r in rows]

    @staticmethod
    def best_selling_products(start, end, limit=20):
        rows = Order.objects.filter(payment_status__in=["paid", "partially_refunded", "refunded"],
                                    paid_at__gte=start, paid_at__lt=end) \
            .values("items__product_id", "items__product__name", "items__product__sku") \
            .annotate(units=Coalesce(Sum("items__quantity"), 0), revenue=Coalesce(Sum("items__line_total"), Decimal("0"), output_field=MONEY)) \
            .order_by("-units")[:limit]
        return [{"product_id": r["items__product_id"], "name": r["items__product__name"], "sku": r["items__product__sku"],
                 "units": int(r["units"] or 0), "revenue": str(r["revenue"])} for r in rows]

    @staticmethod
    def payment_ledger(start, end):
        rows = Payment.objects.filter(created_at__gte=start, created_at__lt=end) \
            .select_related("order").order_by("-created_at")[:5000]
        return [{"reference": p.reference, "order_reference": p.order.reference, "provider": p.provider,
                 "provider_reference": p.provider_reference, "amount": str(p.amount), "currency": p.currency,
                 "status": p.status, "channel": p.channel, "initialized_at": p.initialized_at.isoformat() if p.initialized_at else None,
                 "verified_at": p.verified_at.isoformat() if p.verified_at else None} for p in rows]

    @staticmethod
    def refund_ledger(start, end):
        rows = Refund.objects.filter(created_at__gte=start, created_at__lt=end).select_related("order")[:5000]
        return [{"reference": r.reference, "order_reference": r.order.reference, "requested_amount": str(r.requested_amount),
                 "approved_amount": str(r.approved_amount) if r.approved_amount else None, "status": r.status,
                 "processed_at": r.processed_at.isoformat() if r.processed_at else None} for r in rows]

    @staticmethod
    def inventory_health():
        from apps.inventory.models import Inventory
        from apps.products.models import Product
        total_units = Inventory.objects.aggregate(t=Coalesce(Sum(F("on_hand") - F("reserved")), 0))["t"] or 0
        low = [i for i in Inventory.objects.select_related("product", "variation").all() if i.is_low_stock]
        out = [i for i in Inventory.objects.select_related("product", "variation").all() if i.is_out_of_stock]
        return {
            "total_active_products": Product.objects.filter(status=Product.Status.ACTIVE, is_active=True).count(),
            "total_units_available": int(total_units),
            "low_stock_count": len(low),
            "out_of_stock_count": len(out),
            "low_stock_items": [{"sku": i.product.sku, "name": i.product.name,
                                 "variation": i.variation.sku if i.variation else None, "available": i.available}
                                for i in low[:50]],
            "out_of_stock_items": [{"sku": i.product.sku, "name": i.product.name,
                                    "variation": i.variation.sku if i.variation else None}
                                   for i in out[:50]],
        }
