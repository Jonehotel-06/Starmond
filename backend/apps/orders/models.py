from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.references import order_reference


class OrderQuerySet(models.QuerySet):
    def paid(self):
        return self.filter(payment_status__in=[
            Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED, Order.PaymentStatus.REFUNDED])


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        PAID = "paid", "Paid / confirmed"
        PROCESSING = "processing", "Processing"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        EXPIRED = "expired", "Expired"
        REFUND_REQUESTED = "refund_requested", "Refund requested"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"
        REFUNDED = "refunded", "Refunded"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    class Source(models.TextChoices):
        CART = "cart", "Cart checkout"
        BUY_NOW = "buy_now", "Buy now"

    reference = models.CharField(max_length=32, unique=True, db_index=True, default=order_reference)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="orders")
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.CART)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True)
    # Money — always Decimal, always computed by the backend
    currency = models.CharField(max_length=3, default="NGN")
    subtotal_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    shipping_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    promotion = models.ForeignKey("promotions.Promotion", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    promotion_code_snapshot = models.CharField(max_length=40, blank=True)
    # Customer contact snapshot (guest checkout supported)
    contact_full_name = models.CharField(max_length=150)
    contact_email = models.EmailField(db_index=True)
    contact_phone = models.CharField(max_length=30)
    # Delivery snapshot
    delivery_full_name = models.CharField(max_length=150)
    delivery_phone = models.CharField(max_length=30)
    delivery_state = models.CharField(max_length=80, db_index=True)
    delivery_city = models.CharField(max_length=80)
    delivery_street = models.CharField(max_length=255)
    delivery_details = models.CharField(max_length=255, blank=True)
    delivery_instructions = models.TextField(blank=True)
    shipping_method_id = models.PositiveIntegerField(null=True, blank=True)
    shipping_method_name = models.CharField(max_length=120, blank=True)
    shipping_method_kind = models.CharField(max_length=10, blank=True)
    shipping_estimate = models.CharField(max_length=120, blank=True)
    # Fulfilment
    tracking_reference = models.CharField(max_length=120, blank=True)
    delivery_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    # Lifecycle timestamps
    placed_at = models.DateTimeField(default=timezone.now, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True,
                                      help_text="Pending-payment expiry; reservations release afterwards.")
    # Integrity controls
    idempotency_key = models.CharField(max_length=80, unique=True, null=True, blank=True, db_index=True)
    guest_access_token = models.CharField(max_length=255, blank=True, help_text="Expiring signed access token for guest order links.")

    objects = OrderQuerySet.as_manager()

    class Meta:
        db_table = "orders_order"
        ordering = ["-placed_at"]
        indexes = [
            models.Index(fields=["status", "placed_at"]),
            models.Index(fields=["payment_status", "placed_at"]),
            models.Index(fields=["contact_email"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(total_amount__gte=0), name="order_total_non_negative"),
            models.CheckConstraint(check=models.Q(discount_amount__gte=0), name="order_discount_non_negative"),
            models.CheckConstraint(check=models.Q(shipping_fee__gte=0), name="order_shipping_non_negative"),
        ]

    def __str__(self):
        return self.reference

    @property
    def is_pending_payment(self):
        return self.status == self.Status.PENDING_PAYMENT

    @property
    def is_cancelled_like(self):
        return self.status in (self.Status.CANCELLED, self.Status.EXPIRED)

    @property
    def total_refunded(self):
        from apps.refunds.models import Refund
        from django.db.models import Sum
        total = self.refunds.filter(status=Refund.Status.SUCCESSFUL).aggregate(t=Sum("approved_amount"))["t"]
        return total or Decimal("0.00")


class OrderItem(models.Model):
    """Immutable line-item snapshot — price and name captured at purchase time
    so later catalogue changes never rewrite financial history."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="order_items")
    variation = models.ForeignKey("products.ProductVariation", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=64)
    variation_label = models.CharField(max_length=160, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    customization = models.JSONField(default=dict, blank=True, help_text="Made-to-order details (size, measurements, fabric, ...).")
    reference_image = models.ForeignKey("media.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")

    class Meta:
        db_table = "orders_orderitem"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="order_item_quantity_positive"),
            models.CheckConstraint(check=models.Q(line_total__gte=0), name="order_item_total_non_negative"),
        ]

    def __str__(self):
        return f"{self.order.reference}:{self.sku} x{self.quantity}"


class OrderStatusLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_logs")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_status_logs")
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "orders_statuslog"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.reference}:{self.from_status}->{self.to_status}"
