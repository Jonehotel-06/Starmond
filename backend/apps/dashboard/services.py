"""DashboardService — real, database-driven administration statistics."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.categories.models import Category
from apps.core.models import PublishableModel
from apps.core.utils import money
from apps.inventory.models import Inventory
from apps.inventory.services import InventoryService
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.products.models import Product
from apps.refunds.models import Refund

User = get_user_model()
ZERO = Decimal("0.00")


def _total(qs, field: str) -> Decimal:
    return money(
        qs.aggregate(total=Coalesce(Sum(field), Value(ZERO), output_field=DecimalField()))["total"]
    )


class DashboardService:
    @staticmethod
    def overview(days: int = 30) -> dict:
        now = timezone.now()
        since = now - timedelta(days=days)

        paid_statuses = [
            Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED,
            Order.PaymentStatus.REFUNDED,
        ]

        paid_orders = Order.objects.filter(payment_status__in=paid_statuses, paid_at__gte=since)
        revenue = _total(
            Payment.objects.filter(is_verified=True, paid_at__gte=since), "amount_verified"
        )
        refunds = _total(
            Refund.objects.filter(status=Refund.Status.COMPLETED, completed_at__gte=since),
            "amount_refunded",
        )

        return {
            "generated_at": now.isoformat(),
            "range_days": days,
            "revenue": {
                "gross_revenue": str(money(revenue)),
                "refunds": str(money(refunds)),
                "net_revenue": str(money(revenue - refunds)),
                "currency": "NGN",
            },
            "orders": {
                "total": Order.objects.count(),
                "in_range": Order.objects.filter(created_at__gte=since).count(),
                "paid_in_range": paid_orders.count(),
                "awaiting_payment": Order.objects.filter(
                    status=Order.Status.PENDING_PAYMENT
                ).count(),
                "awaiting_fulfilment": Order.objects.filter(
                    status__in=[Order.Status.PAID, Order.Status.PROCESSING, Order.Status.PACKING]
                ).count(),
                "in_transit": Order.objects.filter(
                    status__in=[Order.Status.DISPATCHED, Order.Status.OUT_FOR_DELIVERY]
                ).count(),
                "average_order_value": str(
                    money(_total(paid_orders, "grand_total") / max(paid_orders.count(), 1))
                ),
            },
            "catalogue": {
                "total_products": Product.objects.alive().count(),
                "published_products": Product.objects.public().count(),
                "draft_products": Product.objects.filter(
                    status=PublishableModel.Status.DRAFT
                ).count(),
                "out_of_stock": Inventory.objects.filter(
                    track_inventory=True, quantity_on_hand__lte=F("quantity_reserved")
                ).count(),
                "low_stock": Inventory.objects.filter(
                    track_inventory=True, quantity_on_hand__gt=F("quantity_reserved"),
                    quantity_on_hand__lte=F("low_stock_threshold"),
                ).count(),
                "total_categories": Category.objects.count(),
                "variation_based_products": Product.objects.filter(
                    is_variation_based=True
                ).count(),
            },
            "customers": {
                "total": User.objects.filter(is_staff=False).count(),
                "new_in_range": User.objects.filter(is_staff=False, date_joined__gte=since).count(),
                "with_orders": User.objects.filter(
                    is_staff=False, orders__payment_status__in=paid_statuses
                ).distinct().count(),
            },
            "payments": {
                "successful_in_range": Payment.objects.filter(
                    is_verified=True, paid_at__gte=since
                ).count(),
                "pending": Payment.objects.filter(
                    status__in=[Payment.Status.INITIALIZED, Payment.Status.PENDING]
                ).count(),
                "failed_in_range": Payment.objects.filter(
                    status=Payment.Status.FAILED, created_at__gte=since
                ).count(),
            },
            "refunds": {
                "open": Refund.objects.filter(
                    status__in=[
                        Refund.Status.REQUESTED, Refund.Status.UNDER_REVIEW,
                        Refund.Status.APPROVED, Refund.Status.PROCESSING,
                    ]
                ).count(),
                "completed_in_range": Refund.objects.filter(
                    status=Refund.Status.COMPLETED, completed_at__gte=since
                ).count(),
            },
        }

    @staticmethod
    def recent_orders(limit: int = 10) -> list[dict]:
        rows = Order.objects.select_related("customer").order_by("-created_at")[:limit]
        return [
            {
                "order_number": order.order_number,
                "customer": order.customer_name,
                "status": order.status,
                "payment_status": order.payment_status,
                "total": str(money(order.grand_total)),
                "created_at": order.created_at.isoformat(),
            }
            for order in rows
        ]

    @staticmethod
    def low_stock_alerts(limit: int = 25) -> list[dict]:
        rows = InventoryService.low_stock()[:limit]
        return [
            {
                "product": row.product.name,
                "sku": row.variation.sku if row.variation_id else row.product.sku,
                "on_hand": row.quantity_on_hand,
                "reserved": row.quantity_reserved,
                "available": row.available_quantity,
                "threshold": row.low_stock_threshold,
            }
            for row in rows
        ]

    @staticmethod
    def top_products(days: int = 30, limit: int = 5) -> list[dict]:
        since = timezone.now() - timedelta(days=days)
        rows = (
            Product.objects.public()
            .filter(order_items__order__paid_at__gte=since)
            .annotate(units=Sum("order_items__quantity"))
            .filter(units__gt=0)
            .order_by("-units")[:limit]
        )
        return [{"product": p.name, "sku": p.sku, "units_sold": p.units} for p in rows]
