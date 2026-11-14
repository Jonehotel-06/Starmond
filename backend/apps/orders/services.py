"""OrderService — validated lifecycle transitions, cancellation and expiry.
All financial status changes are driven by the payment layer, never directly
by staff edits."""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.references import order_reference

from .models import Order, OrderStatusLog

logger = logging.getLogger("starmond.orders")

TRANSITIONS = {
    Order.Status.PENDING_PAYMENT: {Order.Status.PAID, Order.Status.CANCELLED, Order.Status.EXPIRED, Order.Status.PAYMENT_FAILED},
    Order.Status.PAYMENT_FAILED: {Order.Status.PENDING_PAYMENT, Order.Status.CANCELLED, Order.Status.EXPIRED, Order.Status.PAID},
    Order.Status.PAID: {Order.Status.PROCESSING, Order.Status.CANCELLED, Order.Status.REFUND_REQUESTED},
    Order.Status.PROCESSING: {Order.Status.PACKED, Order.Status.CANCELLED, Order.Status.REFUND_REQUESTED},
    Order.Status.PACKED: {Order.Status.SHIPPED, Order.Status.REFUND_REQUESTED},
    Order.Status.SHIPPED: {Order.Status.OUT_FOR_DELIVERY, Order.Status.REFUND_REQUESTED},
    Order.Status.OUT_FOR_DELIVERY: {Order.Status.DELIVERED, Order.Status.REFUND_REQUESTED},
    Order.Status.DELIVERED: {Order.Status.COMPLETED, Order.Status.REFUND_REQUESTED},
    Order.Status.COMPLETED: {Order.Status.REFUND_REQUESTED},
    Order.Status.REFUND_REQUESTED: {Order.Status.PARTIALLY_REFUNDED, Order.Status.REFUNDED,
                                     Order.Status.PROCESSING, Order.Status.DELIVERED, Order.Status.COMPLETED},
    Order.Status.PARTIALLY_REFUNDED: {Order.Status.REFUNDED, Order.Status.PROCESSING, Order.Status.COMPLETED},
    Order.Status.CANCELLED: set(),
    Order.Status.EXPIRED: set(),
    Order.Status.REFUNDED: set(),
}


class OrderService:
    @staticmethod
    def can_transition(order, new_status):
        return new_status in TRANSITIONS.get(order.status, set())

    @staticmethod
    @transaction.atomic
    def transition(order, new_status, actor=None, note=""):
        if order.status == new_status:
            return order
        if not OrderService.can_transition(order, new_status):
            raise ServiceError(
                f"Invalid order status transition: {order.status} -> {new_status}.",
                code="invalid_status_transition", status_code=409)
        old = order.status
        order.status = new_status
        now = timezone.now()
        if new_status == Order.Status.PAID and not order.paid_at:
            order.paid_at = now
            order.payment_status = Order.PaymentStatus.PAID
        if new_status == Order.Status.SHIPPED:
            order.shipped_at = now
        if new_status == Order.Status.DELIVERED:
            order.delivered_at = now
        if new_status == Order.Status.COMPLETED:
            order.completed_at = now
        if new_status in (Order.Status.CANCELLED, Order.Status.EXPIRED):
            order.cancelled_at = now
            if order.payment_status == Order.PaymentStatus.PENDING:
                order.payment_status = Order.PaymentStatus.EXPIRED if new_status == Order.Status.EXPIRED else Order.PaymentStatus.FAILED
        if new_status == Order.Status.PAYMENT_FAILED:
            order.payment_status = Order.PaymentStatus.FAILED
        if new_status == Order.Status.REFUNDED:
            order.payment_status = Order.PaymentStatus.REFUNDED
        if new_status == Order.Status.PARTIALLY_REFUNDED:
            order.payment_status = Order.PaymentStatus.PARTIALLY_REFUNDED
        order.save()
        OrderStatusLog.objects.create(order=order, from_status=old, to_status=new_status,
                                      actor=actor if getattr(actor, "is_authenticated", False) else None,
                                      note=note[:255])
        return order

    @staticmethod
    @transaction.atomic
    def confirm_paid(order, payment):
        """Called ONLY after server-side payment verification succeeds.
        Finalizes inventory reservations into sales."""
        from apps.inventory.services import InventoryService
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.payment_status == Order.PaymentStatus.PAID and order.status != Order.Status.PENDING_PAYMENT:
            return order  # idempotent
        for item in order.items.select_related("variation"):
            inventory = InventoryService.resolve_inventory(item.product, item.variation)
            if inventory:
                InventoryService.confirm_sale(inventory, item.quantity, order=order)
        OrderService.transition(order, Order.Status.PAID, note=f"Payment {payment.reference} verified")
        return order

    @staticmethod
    @transaction.atomic
    def cancel(order, actor=None, note="Cancelled", release_stock=True):
        from apps.inventory.services import InventoryService
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status in (Order.Status.CANCELLED, Order.Status.EXPIRED):
            return order
        if order.payment_status == Order.PaymentStatus.PAID:
            raise ServiceError(
                "Paid orders cannot be cancelled directly — use the refund workflow.",
                code="paid_order_cancel", status_code=409)
        if release_stock:
            for item in order.items.select_related("variation"):
                inventory = InventoryService.resolve_inventory(item.product, item.variation)
                if inventory:
                    InventoryService.release(inventory, item.quantity, order=order, reason=note)
        OrderService.transition(order, Order.Status.CANCELLED, actor=actor, note=note)
        return order

    @staticmethod
    def expire_stale_pending_orders():
        """Release reservations for pending orders past their expiry window."""
        now = timezone.now()
        stale = Order.objects.filter(status=Order.Status.PENDING_PAYMENT, expires_at__lt=now)
        count = 0
        for order in stale:
            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(pk=order.pk)
                    if order.status != Order.Status.PENDING_PAYMENT:
                        continue
                    from apps.inventory.services import InventoryService
                    for item in order.items.select_related("variation"):
                        inventory = InventoryService.resolve_inventory(item.product, item.variation)
                        if inventory:
                            InventoryService.release(inventory, item.quantity, order=order, reason="Pending payment expired")
                    OrderService.transition(order, Order.Status.EXPIRED, note="Auto-expired: payment window elapsed")
                    count += 1
            except Exception:
                logger.exception("Failed expiring order %s", order.reference)
        return count

    @staticmethod
    def make_reference():
        for _ in range(6):
            ref = order_reference()
            if not Order.objects.filter(reference=ref).exists():
                return ref
        raise ServiceError("Could not allocate an order reference. Retry.", code="reference_collision", status_code=503)
