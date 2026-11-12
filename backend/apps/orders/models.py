"""
Orders: lifecycle, immutable line snapshots and the activity trail.

Every money field here is written by ``PricingService`` on the server. Line
items snapshot the product name, SKU and unit price at purchase time so later
catalogue edits can never rewrite historical financial records.
"""
from __future__ import annotations

import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, TimeStampedModel


class OrderNumberSequence(models.Model):
    """Daily counter used to build human-readable, non-guessable order numbers."""

    day = models.DateField(unique=True)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "orders_number_sequence"

    def __str__(self) -> str:
        return f"{self.day}: {self.last_value}"


class Order(BaseModel):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        PAID = "paid", "Paid"
        PROCESSING = "processing", "Processing"
        PACKING = "packing", "Packing"
        DISPATCHED = "dispatched", "Dispatched"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"
        REFUNDED = "refunded", "Refunded"

    class Channel(models.TextChoices):
        WEB_CART = "web_cart", "Website cart"
        BUY_NOW = "buy_now", "Buy now"
        ADMIN = "admin", "Created by staff"

    # -- identity ----------------------------------------------------------
    order_number = models.CharField(max_length=32, unique=True, db_index=True, editable=False)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WEB_CART)

    # -- ownership ---------------------------------------------------------
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="orders",
    )
    guest_email = models.EmailField(blank=True, db_index=True)
    guest_phone = models.CharField(max_length=16, blank=True)
    guest_access_token_hash = models.CharField(
        max_length=64, blank=True,
        help_text="SHA-256 of the signed access token issued to a guest for order tracking.",
    )

    # -- state -------------------------------------------------------------
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True
    )
    payment_status = models.CharField(
        max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, db_index=True
    )

    # -- money (all server-computed) --------------------------------------
    currency = models.CharField(max_length=3, default="NGN")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    shipping_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_refunded = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    applied_promotion_codes = models.JSONField(default=list, blank=True)

    # -- delivery snapshot -------------------------------------------------
    shipping_full_name = models.CharField(max_length=150, blank=True)
    shipping_phone = models.CharField(max_length=16, blank=True)
    shipping_email = models.EmailField(blank=True)
    shipping_address_line = models.CharField(max_length=255, blank=True)
    shipping_apartment = models.CharField(max_length=120, blank=True)
    shipping_city = models.CharField(max_length=80, blank=True, db_index=True)
    shipping_state = models.CharField(max_length=80, blank=True, db_index=True)
    shipping_lga = models.CharField(max_length=80, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)
    shipping_country = models.CharField(max_length=80, default="Nigeria")
    delivery_instructions = models.TextField(blank=True)
    shipping_zone = models.ForeignKey(
        "shipping.ShippingZone", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="orders",
    )
    shipping_method = models.ForeignKey(
        "shipping.ShippingMethod", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="orders",
    )
    shipping_method_name = models.CharField(max_length=120, blank=True)
    estimated_delivery_days_min = models.PositiveSmallIntegerField(null=True, blank=True)
    estimated_delivery_days_max = models.PositiveSmallIntegerField(null=True, blank=True)
    is_pickup = models.BooleanField(default=False)

    # -- notes -------------------------------------------------------------
    customer_note = models.TextField(blank=True)
    internal_note = models.TextField(blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)

    # -- provenance --------------------------------------------------------
    cart = models.ForeignKey(
        "cart.Cart", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True, db_index=True)

    # -- timestamps --------------------------------------------------------
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    processing_at = models.DateTimeField(null=True, blank=True)
    packed_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    stock_committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "orders_order"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "payment_status"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["guest_email"]),
            models.Index(fields=["shipping_state"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(grand_total__gte=0), name="order_total_non_negative"),
            models.CheckConstraint(
                check=models.Q(amount_refunded__lte=models.F("amount_paid")),
                name="order_refunded_lte_paid",
            ),
        ]

    def __str__(self) -> str:
        return self.order_number

    # -- derived state -----------------------------------------------------
    @property
    def is_paid(self) -> bool:
        return self.payment_status in {
            self.PaymentStatus.PAID,
            self.PaymentStatus.PARTIALLY_REFUNDED,
            self.PaymentStatus.REFUNDED,
        }

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.COMPLETED, self.Status.CANCELLED, self.Status.EXPIRED}

    @property
    def is_cancellable(self) -> bool:
        return self.status in {
            self.Status.PENDING_PAYMENT, self.Status.PAID, self.Status.PROCESSING,
        }

    @property
    def is_refundable(self) -> bool:
        return self.is_paid and self.amount_refunded < self.amount_paid and self.status in {
            self.Status.PAID, self.Status.PROCESSING, self.Status.PACKING,
            self.Status.DISPATCHED, self.Status.OUT_FOR_DELIVERY,
            self.Status.DELIVERED, self.Status.COMPLETED,
        }

    @property
    def net_total(self) -> Decimal:
        """What the business actually keeps after refunds."""
        return (self.amount_paid or Decimal("0")) - (self.amount_refunded or Decimal("0"))

    @property
    def customer_email(self) -> str:
        return self.guest_email or (
            getattr(self.customer, "email", "") if self.customer_id else ""
        )

    @property
    def customer_name(self) -> str:
        return self.shipping_full_name or (
            getattr(self.customer, "display_name", "") if self.customer_id else "Guest"
        )

    @property
    def item_count(self) -> int:
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    @property
    def fulfilment_progress(self) -> int:
        """0–100 progress used by the customer's order tracker."""
        order_of = [
            self.Status.PENDING_PAYMENT, self.Status.PAID, self.Status.PROCESSING,
            self.Status.PACKING, self.Status.DISPATCHED, self.Status.OUT_FOR_DELIVERY,
            self.Status.DELIVERED, self.Status.COMPLETED,
        ]
        if self.status in {self.Status.CANCELLED, self.Status.EXPIRED}:
            return 0
        try:
            return int(order_of.index(self.status) / (len(order_of) - 1) * 100)
        except ValueError:
            return 0

    @property
    def status_label(self) -> str:
        return self.get_status_display()

    def new_guest_token(self) -> str:
        """Issues a fresh guest access token and stores only its hash."""
        import hashlib

        raw = secrets.token_urlsafe(32)
        self.guest_access_token_hash = hashlib.sha256(raw.encode()).hexdigest()
        return raw

    def verify_guest_token(self, raw: str) -> bool:
        import hashlib

        if not self.guest_access_token_hash or not raw:
            return False
        return secrets.compare_digest(
            self.guest_access_token_hash, hashlib.sha256(raw.encode()).hexdigest()
        )

    def recalculate_amount_due(self, save: bool = True) -> Decimal:
        self.amount_due = max(
            (self.grand_total or Decimal("0"))
            - (self.amount_paid or Decimal("0"))
            + (self.amount_refunded or Decimal("0")),
            Decimal("0"),
        )
        if save:
            self.save(update_fields=["amount_due", "updated_at"])
        return self.amount_due


class OrderItem(BaseModel):
    """Immutable snapshot of one purchased line."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.PROTECT, related_name="order_items"
    )
    variation = models.ForeignKey(
        "products.ProductVariation", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="order_items",
    )
    # snapshots — never updated after creation
    product_name = models.CharField(max_length=220)
    variation_label = models.CharField(max_length=220, blank=True)
    sku = models.CharField(max_length=64)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    line_subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    discount_allocated = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cost_price_snapshot = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Internal margin reporting only.",
    )
    category_name = models.CharField(max_length=150, blank=True)
    custom_order_details = models.JSONField(default=dict, blank=True)
    refunded_quantity = models.PositiveIntegerField(default=0)
    is_fully_refunded = models.BooleanField(default=False)

    class Meta:
        db_table = "orders_item"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gte=1), name="order_item_quantity_positive"),
            models.CheckConstraint(check=models.Q(unit_price__gte=0), name="order_item_price_non_negative"),
            models.CheckConstraint(
                check=models.Q(refunded_quantity__lte=models.F("quantity")),
                name="order_item_refunded_within_quantity",
            ),
        ]
        indexes = [models.Index(fields=["order"]), models.Index(fields=["product"])]

    def __str__(self) -> str:
        return f"{self.product_name} x{self.quantity}"

    @property
    def display_name(self) -> str:
        return f"{self.product_name} ({self.variation_label})" if self.variation_label else self.product_name

    @property
    def refundable_quantity(self) -> int:
        return max(self.quantity - self.refunded_quantity, 0)

    def save(self, *a, **kw):
        if not self._state.adding:
            # Line money is immutable; only refund counters may change.
            allowed = {"refunded_quantity", "is_fully_refunded", "updated_at"}
            update_fields = kw.get("update_fields")
            if update_fields is not None:
                forbidden = set(update_fields) - allowed
                if forbidden:
                    raise PermissionError(
                        f"Order line fields are immutable after creation: {sorted(forbidden)}"
                    )
        return super().save(*a, **kw)


class OrderActivity(BaseModel):
    """Human-readable timeline shown to customers and staff."""

    class Event(models.TextChoices):
        CREATED = "created", "Order created"
        PAYMENT_INITIATED = "payment_initiated", "Payment initiated"
        PAYMENT_CONFIRMED = "payment_confirmed", "Payment confirmed"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        PAYMENT_RETRY = "payment_retry", "Payment retried"
        STATE_CHANGED = "state_changed", "Status changed"
        SHIPMENT_CREATED = "shipment_created", "Shipment created"
        SHIPMENT_UPDATED = "shipment_updated", "Shipment updated"
        TRACKING_UPDATED = "tracking_updated", "Tracking updated"
        CANCELLED = "cancelled", "Order cancelled"
        EXPIRED = "expired", "Order expired"
        REFUND_REQUESTED = "refund_requested", "Refund requested"
        REFUND_PROCESSED = "refund_processed", "Refund processed"
        NOTE = "note", "Note"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="activities")
    event = models.CharField(max_length=40, choices=Event.choices, db_index=True)
    message = models.CharField(max_length=300)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="order_activities",
    )
    actor_label = models.CharField(max_length=120, blank=True)
    is_customer_visible = models.BooleanField(default=True)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "orders_activity"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.event}: {self.message}"

class GuestOrderLink(TimeStampedModel):
    """Expiring signed link that lets a guest reopen their order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="guest_links")
    token_hash = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "orders_guest_link"
