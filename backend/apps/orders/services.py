"""
OrderService — order lifecycle, state machine and settlement.

The state machine is enforced here, never in a view:

    pending_payment → paid → processing → packing → dispatched
      → out_for_delivery → delivered → completed
    pending_payment → cancelled | expired

Transitioning to *any* other state raises ``InvalidStateTransition``.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.audit.services import AuditService
from apps.core.exceptions import (
    ConflictError,
    InsufficientStock,
    InvalidStateTransition,
    NotFound,
    ValidationError,
)
from apps.core.utils import money
from apps.orders.models import Order, OrderActivity, OrderItem, OrderNumberSequence
from apps.orders.pricing import BasketLine, PriceBreakdown, PricingService

logger = logging.getLogger("apps.orders")


# Explicit, auditable state machine.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    Order.Status.PENDING_PAYMENT: {
        Order.Status.PAID, Order.Status.CANCELLED, Order.Status.EXPIRED,
    },
    Order.Status.PAID: {
        Order.Status.PROCESSING, Order.Status.CANCELLED,
    },
    Order.Status.PROCESSING: {
        Order.Status.PACKING, Order.Status.CANCELLED,
    },
    Order.Status.PACKING: {
        Order.Status.DISPATCHED, Order.Status.CANCELLED,
    },
    Order.Status.DISPATCHED: {
        Order.Status.OUT_FOR_DELIVERY, Order.Status.COMPLETED, Order.Status.DELIVERED,
    },
    Order.Status.OUT_FOR_DELIVERY: {
        Order.Status.DELIVERED, Order.Status.COMPLETED,
    },
    Order.Status.DELIVERED: {Order.Status.COMPLETED},
    Order.Status.COMPLETED: set(),
    Order.Status.CANCELLED: set(),
    Order.Status.EXPIRED: set(),
}

TERMINAL = {Order.Status.COMPLETED, Order.Status.CANCELLED, Order.Status.EXPIRED}

# Canonical forward chain used when a fulfilment milestone implies earlier steps.
FULFILMENT_CHAIN = [
    Order.Status.PENDING_PAYMENT,
    Order.Status.PAID,
    Order.Status.PROCESSING,
    Order.Status.PACKING,
    Order.Status.DISPATCHED,
    Order.Status.OUT_FOR_DELIVERY,
    Order.Status.DELIVERED,
    Order.Status.COMPLETED,
]


class OrderService:
    # ------------------------------------------------------------------
    # Numbering
    # ------------------------------------------------------------------
    @staticmethod
    def generate_order_number() -> str:
        """Human-readable and non-sequential: ``STM-YYMMDD-0007``."""
        today = timezone.localdate()
        with transaction.atomic():
            sequence, _ = OrderNumberSequence.objects.select_for_update().get_or_create(
                day=today, defaults={"last_value": 0}
            )
            sequence.last_value = F("last_value") + 1
            sequence.save(update_fields=["last_value"])
            sequence.refresh_from_db(fields=["last_value"])
            return f"STM-{today:%y%m%d}-{sequence.last_value:05d}"

    # ------------------------------------------------------------------
    # Creation (used by CheckoutService only)
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def create_order(
        *,
        lines: list[BasketLine],
        breakdown: PriceBreakdown,
        customer=None,
        guest_email: str = "",
        guest_phone: str = "",
        shipping: dict | None = None,
        channel: str = Order.Channel.WEB_CART,
        cart=None,
        customer_note: str = "",
        source_ip: str | None = None,
        user_agent: str = "",
        idempotency_key: str = "",
        promotion_codes: list[str] | None = None,
    ) -> Order:
        """
        Persists an order, reserves its stock and records promotions — all inside
        one transaction, so a failure at any step leaves nothing behind.
        """
        if not lines:
            raise ValidationError("Your cart is empty.")
        if not breakdown.shipping_eligible:
            raise ValidationError(
                breakdown.shipping.get("reason") or "We cannot deliver to this address."
            )

        shipping = shipping or {}
        email = (guest_email or getattr(customer, "email", "") or "").strip().lower()
        if not email:
            raise ValidationError("An email address is required so we can send your receipt.")

        now = timezone.now()
        order = Order(
            order_number=OrderService.generate_order_number(),
            channel=channel,
            customer=customer if getattr(customer, "pk", None) else None,
            guest_email="" if customer else email,
            guest_phone="" if customer else guest_phone,
            status=Order.Status.PENDING_PAYMENT,
            payment_status=Order.PaymentStatus.UNPAID,
            currency=breakdown.currency,
            subtotal=money(breakdown.subtotal),
            discount_total=money(breakdown.discount_total),
            shipping_total=money(breakdown.shipping_total),
            tax_total=money(breakdown.tax_total),
            grand_total=money(breakdown.grand_total),
            amount_paid=Decimal("0.00"),
            amount_refunded=Decimal("0.00"),
            amount_due=money(breakdown.grand_total),
            applied_promotion_codes=promotion_codes or [],
            shipping_full_name=str(shipping.get("full_name", ""))[:150],
            shipping_phone=str(shipping.get("phone", ""))[:16],
            shipping_email=email,
            shipping_address_line=str(shipping.get("address_line", ""))[:255],
            shipping_apartment=str(shipping.get("apartment", ""))[:120],
            shipping_city=str(shipping.get("city", ""))[:80],
            shipping_state=str(shipping.get("state", ""))[:80],
            shipping_lga=str(shipping.get("lga", ""))[:80],
            shipping_postal_code=str(shipping.get("postal_code", ""))[:20],
            shipping_country=str(shipping.get("country", "Nigeria"))[:80],
            delivery_instructions=str(shipping.get("delivery_instructions", ""))[:2000],
            customer_note=customer_note[:2000],
            cart=cart,
            source_ip=source_ip,
            user_agent=user_agent[:255],
            idempotency_key=idempotency_key[:255],
            expires_at=now + timedelta(minutes=settings.ORDER_EXPIRY_MINUTES),
        )

        if breakdown.shipping.get("shipping_method_id"):
            from apps.shipping.models import ShippingMethod

            method = ShippingMethod.objects.filter(
                pk=breakdown.shipping["shipping_method_id"]
            ).first()
            if method is not None:
                order.shipping_method = method
                order.shipping_zone = method.zone
                order.shipping_method_name = method.name
                order.estimated_delivery_days_min = method.estimated_days_min
                order.estimated_delivery_days_max = method.estimated_days_max
                order.is_pickup = method.kind == ShippingMethod.Kind.PICKUP

        order.save()

        # ---- lines --------------------------------------------------------
        allocations = PricingService.allocate_line_discounts(lines, breakdown.discount_total)
        for line, allocation in zip(lines, allocations):
            from apps.products.models import Product, ProductVariation

            product = Product.objects.get(pk=line.product_id)
            variation = (
                ProductVariation.objects.get(pk=line.variation_id) if line.variation_id else None
            )
            OrderItem.objects.create(
                order=order,
                product=product,
                variation=variation,
                product_name=line.name,
                variation_label=line.variation_label,
                sku=line.sku,
                unit_price=money(line.unit_price),
                quantity=line.quantity,
                line_subtotal=line.line_subtotal,
                discount_allocated=money(allocation),
                line_total=money(line.line_subtotal - allocation),
                tax_amount=money(line.unit_price * line.quantity * line.tax_rate_percent / 100),
                cost_price_snapshot=product.cost_price,
                category_name=product.category.name if product.category_id else "",
                custom_order_details=line.custom_order_details or {},
            )

        # ---- stock reservation (raises → whole order rolls back) ----------
        from apps.inventory.services import InventoryService

        InventoryService.reserve_for_order(order)

        # ---- promotions ----------------------------------------------------
        from apps.promotions.models import Promotion
        from apps.promotions.services import PromotionService

        for discount in breakdown.applied_discounts:
            if not discount.get("promotion_id"):
                continue
            promotion = Promotion.objects.filter(pk=discount["promotion_id"]).first()
            if promotion is None:
                continue
            PromotionService.record_usage(
                promotion=promotion,
                order=order,
                discount_amount=discount["discount_amount"],
                user=customer,
                email=email,
            )

        # ---- trail ---------------------------------------------------------
        OrderService.add_activity(
            order,
            event=OrderActivity.Event.CREATED,
            message=f"Order {order.order_number} created.",
            actor=customer,
            metadata={"channel": channel, "total": str(order.grand_total)},
        )
        AuditService.record(
            action="create",
            entity_type="order",
            entity_id=order.pk,
            actor=customer,
            summary=f"Order {order.order_number} created ({channel})",
            after={"grand_total": str(order.grand_total), "items": len(lines)},
        )

        try:
            from apps.notifications.services import NotificationService

            NotificationService.order_placed(order)
        except Exception:  # pragma: no cover
            logger.exception("Order-placed notification failed for %s", order.order_number)

        return order

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def transition(order: Order, target: str, *, actor=None, note: str = "") -> Order:
        """Moves an order to ``target``, validating the transition first."""
        locked = Order.objects.select_for_update().get(pk=order.pk)

        if target not in Order.Status.values:
            raise ValidationError(f"Unknown order status '{target}'.")
        if target == locked.status:
            return locked  # idempotent no-op
        allowed = ALLOWED_TRANSITIONS.get(locked.status, set())
        if target not in allowed:
            raise InvalidStateTransition(
                f"An order in '{locked.get_status_display()}' cannot move to '{target}'."
            )
        if target == Order.Status.PAID and not locked.is_paid:
            raise InvalidStateTransition(
                "An order can only be marked paid through a verified payment."
            )

        previous = locked.status
        locked.status = target
        now = timezone.now()

        stamp_fields = {
            Order.Status.PROCESSING: "processing_at",
            Order.Status.PACKING: "packed_at",
            Order.Status.DISPATCHED: "dispatched_at",
            Order.Status.DELIVERED: "delivered_at",
            Order.Status.COMPLETED: "completed_at",
            Order.Status.CANCELLED: "cancelled_at",
            Order.Status.EXPIRED: "expired_at",
            Order.Status.PAID: "paid_at",
        }
        update_fields = ["status", "updated_at"]
        stamp = stamp_fields.get(target)
        if stamp and getattr(locked, stamp) is None:
            setattr(locked, stamp, now)
            update_fields.append(stamp)
        locked.save(update_fields=update_fields)

        OrderService.add_activity(
            locked,
            event=OrderActivity.Event.STATE_CHANGED,
            message=note or f"Status changed from {previous} to {target}.",
            actor=actor,
            metadata={"from": previous, "to": target},
        )
        AuditService.record(
            action="order_state_changed",
            entity_type="order",
            entity_id=locked.pk,
            actor=actor,
            summary=f"{locked.order_number}: {previous} → {target}",
            before={"status": previous},
            after={"status": target},
        )

        try:
            from apps.notifications.services import NotificationService

            NotificationService.order_status_changed(locked, previous)
        except Exception:  # pragma: no cover
            logger.exception("Status notification failed for %s", locked.order_number)

        return locked

    @staticmethod
    @transaction.atomic
    def advance_to(order: Order, target: str, *, actor=None, note: str = "") -> Order:
        """
        Advances an order to ``target`` by stepping through every intermediate
        status in the canonical chain.

        Used by the shipment workflow: dispatching a shipment from "processing"
        legitimately implies "packing → dispatched" happened, but each hop is
        still validated against the state machine and audited individually.
        """
        if target not in FULFILMENT_CHAIN:
            raise ValidationError(f"'{target}' is not part of the fulfilment chain.")

        current = Order.objects.get(pk=order.pk)
        try:
            start = FULFILMENT_CHAIN.index(current.status)
            destination = FULFILMENT_CHAIN.index(target)
        except ValueError:
            raise InvalidStateTransition(
                f"An order in '{current.get_status_display()}' cannot advance to '{target}'."
            )
        if destination <= start:
            return current

        for step in FULFILMENT_CHAIN[start + 1: destination + 1]:
            if step == Order.Status.PAID:
                raise InvalidStateTransition(
                    "An order can only be marked paid through a verified payment."
                )
            current = OrderService.transition(
                current, step, actor=actor,
                note=note if step == target else f"Auto-advanced to {step}.",
            )
        return current

    # ------------------------------------------------------------------
    # Payment settlement
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def mark_paid(order: Order, *, payment, actor=None, source: str = "webhook") -> Order:
        """
        Settles a verified payment.

        Idempotent: a second call (webhook retry, client verification race) finds
        the order already paid and returns without double-counting anything.
        """
        locked = Order.objects.select_for_update().get(pk=order.pk)

        if locked.payment_status == Order.PaymentStatus.PAID:
            logger.info("Order %s already paid; ignoring duplicate settlement", locked.order_number)
            return locked

        if locked.status in {Order.Status.CANCELLED, Order.Status.EXPIRED}:
            # Money arrived after the order lapsed — recognise it and flag for refund.
            logger.warning(
                "Payment received for %s order %s; flagging for manual resolution",
                locked.status, locked.order_number,
            )
            locked.amount_paid = money(locked.amount_paid + money(payment.amount_verified or payment.amount))
            locked.payment_status = Order.PaymentStatus.PAID
            locked.recalculate_amount_due(save=False)
            locked.save(update_fields=["amount_paid", "payment_status", "amount_due", "updated_at"])
            OrderService.add_activity(
                locked,
                event=OrderActivity.Event.PAYMENT_CONFIRMED,
                message=(
                    f"Payment received after the order was {locked.status}. "
                    f"A refund is required."
                ),
                actor=actor,
            )
            AuditService.record(
                action="payment_verified",
                entity_type="order",
                entity_id=locked.pk,
                actor=actor,
                summary=f"Late payment on {locked.order_number} — refund required",
                after={"amount": str(payment.amount_verified)},
            )
            return locked

        previous_status = locked.status
        locked.payment_status = Order.PaymentStatus.PAID
        locked.status = Order.Status.PAID
        locked.paid_at = payment.paid_at or timezone.now()
        locked.amount_paid = money(payment.amount_verified or payment.amount)
        locked.recalculate_amount_due(save=False)
        locked.save(
            update_fields=[
                "payment_status", "status", "paid_at", "amount_paid", "amount_due", "updated_at",
            ]
        )

        # Convert holds into sales.
        from apps.inventory.services import InventoryService

        InventoryService.commit_for_order(locked, reason=f"Paid order {locked.order_number}")
        locked.stock_committed_at = timezone.now()
        locked.save(update_fields=["stock_committed_at", "updated_at"])

        # Cumulative merchandising counters (never used for financial reporting).
        for item in locked.items.all():
            from apps.products.models import Product

            Product.objects.filter(pk=item.product_id).update(
                sold_count=F("sold_count") + item.quantity
            )

        OrderService._update_customer_stats(locked)

        OrderService.add_activity(
            locked,
            event=OrderActivity.Event.PAYMENT_CONFIRMED,
            message=f"Payment of ₦{locked.amount_paid:,.2f} confirmed.",
            actor=actor,
            metadata={
                "payment_reference": payment.reference,
                "source": source,
                "previous_status": previous_status,
            },
        )

        try:
            from apps.notifications.services import NotificationService

            NotificationService.payment_received(locked, payment)
        except Exception:  # pragma: no cover
            logger.exception("Receipt notification failed for %s", locked.order_number)

        return locked

    @staticmethod
    def _update_customer_stats(order: Order) -> None:
        if not order.customer_id:
            return
        from apps.customers.models import CustomerProfile

        profile, _ = CustomerProfile.objects.get_or_create(user_id=order.customer_id)
        CustomerProfile.objects.filter(pk=profile.pk).update(
            order_count=F("order_count") + 1,
            lifetime_value=F("lifetime_value") + order.grand_total,
        )

    # ------------------------------------------------------------------
    # Customer-initiated actions
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def cancel(order: Order, *, actor=None, reason: str = "", by_staff: bool = False) -> Order:
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status == Order.Status.CANCELLED:
            return locked
        if not locked.is_cancellable and not by_staff:
            raise InvalidStateTransition(
                f"An order that is already '{locked.get_status_display()}' can no longer be cancelled."
            )
        if not by_staff and locked.status != Order.Status.PENDING_PAYMENT:
            raise InvalidStateTransition(
                "This order has already been paid. Please request a refund instead."
            )
        if by_staff and locked.status in {Order.Status.DISPATCHED, Order.Status.OUT_FOR_DELIVERY,
                                          Order.Status.DELIVERED, Order.Status.COMPLETED}:
            raise InvalidStateTransition(
                "A dispatched or delivered order cannot be cancelled. Use the refund workflow."
            )

        locked.cancellation_reason = (reason or "Cancelled by customer")[:255]
        locked.save(update_fields=["cancellation_reason", "updated_at"])

        from apps.inventory.services import InventoryService
        from apps.promotions.services import PromotionService

        InventoryService.release_for_order(locked, reason="Order cancelled")
        PromotionService.release_usages_for_order(locked)

        OrderService.add_activity(
            locked,
            event=OrderActivity.Event.CANCELLED,
            message=f"Order cancelled: {locked.cancellation_reason}",
            actor=actor,
        )
        return OrderService.transition(locked, Order.Status.CANCELLED, actor=actor,
                                       note=f"Order cancelled: {locked.cancellation_reason}")

    @staticmethod
    @transaction.atomic
    def expire(order: Order, *, actor=None) -> Order:
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status != Order.Status.PENDING_PAYMENT:
            return locked
        from apps.inventory.services import InventoryService
        from apps.promotions.services import PromotionService

        InventoryService.release_for_order(locked, reason="Order expired", status="expired")
        PromotionService.release_usages_for_order(locked)
        return OrderService.transition(locked, Order.Status.EXPIRED, actor=actor,
                                       note="Order expired before payment.")

    @staticmethod
    def expire_stale_orders() -> dict:
        """Housekeeping job: lapses unpaid orders past their window."""
        now = timezone.now()
        expired = 0
        for order in Order.objects.filter(
            status=Order.Status.PENDING_PAYMENT, expires_at__lt=now
        ).iterator():
            # A pending payment that the provider already accepted is not expired.
            if order.payments.filter(status__in=["success"]).exists():
                continue
            OrderService.expire(order)
            expired += 1
        return {"expired_orders": expired}

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def mark_delivered(order: Order, *, actor=None, note: str = "") -> Order:
        return OrderService.transition(order, Order.Status.DELIVERED, actor=actor,
                                       note=note or "Order delivered to the customer.")

    @staticmethod
    @transaction.atomic
    def complete(order: Order, *, actor=None) -> Order:
        if order.status not in {Order.Status.DELIVERED, Order.Status.DISPATCHED,
                                Order.Status.OUT_FOR_DELIVERY}:
            raise InvalidStateTransition("Only a dispatched or delivered order can be completed.")
        return OrderService.transition(order, Order.Status.COMPLETED, actor=actor,
                                       note="Order completed.")

    # ------------------------------------------------------------------
    # Activity trail
    # ------------------------------------------------------------------
    @staticmethod
    def add_activity(order: Order, *, event: str, message: str, actor=None,
                     is_customer_visible: bool = True, metadata: dict | None = None) -> OrderActivity:
        actor_label = ""
        if actor is not None:
            actor_label = getattr(actor, "display_name", "") or getattr(actor, "email", "") or "staff"
        return OrderActivity.objects.create(
            order=order,
            event=event,
            message=message[:300],
            actor=actor if getattr(actor, "pk", None) else None,
            actor_label=actor_label[:120],
            is_customer_visible=is_customer_visible,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------
    @staticmethod
    def get_customer_order(order_number: str, user) -> Order:
        order = Order.objects.filter(order_number=order_number, customer=user).first()
        if order is None:
            raise NotFound("Order not found.")
        return order

    @staticmethod
    def get_guest_order(order_number: str, token: str) -> Order:
        """
        Guest access with a signed, expiring link.

        A guest who supplies the correct order number but no valid token gets the
        same 404 as a non-existent order — no enumeration signal.
        """
        order = Order.objects.filter(order_number=order_number, customer__isnull=True).first()
        if order is None or not order.verify_guest_token(token):
            raise NotFound("Order not found.")
        return order

    @staticmethod
    def stats_snapshot(order: Order) -> dict:
        return {
            "order_number": order.order_number,
            "status": order.status,
            "status_label": order.get_status_display(),
            "payment_status": order.payment_status,
            "subtotal": str(money(order.subtotal)),
            "discount_total": str(money(order.discount_total)),
            "shipping_total": str(money(order.shipping_total)),
            "grand_total": str(money(order.grand_total)),
            "amount_paid": str(money(order.amount_paid)),
            "amount_refunded": str(money(order.amount_refunded)),
            "currency": order.currency,
            "item_count": order.item_count,
            "placed_at": order.created_at.isoformat(),
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "expires_at": order.expires_at.isoformat() if order.expires_at else None,
            "progress": order.fulfilment_progress,
        }
