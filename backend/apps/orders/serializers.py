"""Order serializers — customer-facing plus staff-facing variants."""
from __future__ import annotations

from rest_framework import serializers

from apps.core.utils import money
from apps.orders.models import Order, OrderActivity, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    refundable_quantity = serializers.IntegerField(read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "variation_label", "sku", "display_name",
                  "unit_price", "quantity", "line_subtotal", "line_total",
                  "discount_allocated", "refunded_quantity", "refundable_quantity",
                  "is_fully_refunded", "custom_order_details", "image"]

    def get_unit_price(self, obj):
        return str(money(obj.unit_price))

    def get_line_total(self, obj):
        return str(money(obj.line_total))

    def get_image(self, obj):
        try:
            image = obj.product.primary_image
            return image.image.url if image else None
        except Exception:
            return None


class OrderActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderActivity
        fields = ["id", "event", "message", "actor_label", "metadata", "created_at"]


class OrderSummarySerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)
    status_label = serializers.CharField(read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["order_number", "status", "status_label", "payment_status", "total",
                  "currency", "item_count", "created_at", "paid_at", "progress"]
        read_only_fields = fields

    total = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    def get_total(self, obj):
        return str(money(obj.grand_total))

    def get_progress(self, obj):
        return obj.fulfilment_progress


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    activities = serializers.SerializerMethodField()
    shipping = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()
    refunds = serializers.SerializerMethodField()
    tracking = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "order_number", "channel", "status", "payment_status", "currency",
            "subtotal", "discount_total", "shipping_total", "tax_total", "grand_total",
            "amount_paid", "amount_refunded", "amount_due", "applied_promotion_codes",
            "items", "shipping", "payments", "refunds", "activities", "tracking",
            "customer_note", "created_at", "paid_at", "expires_at", "delivered_at",
            "completed_at", "cancelled_at", "cancellation_reason",
        ]
        read_only_fields = fields

    def get_activities(self, obj):
        rows = obj.activities.filter(is_customer_visible=True)[:50]
        return OrderActivitySerializer(rows, many=True).data

    def get_shipping(self, obj):
        return {
            "full_name": obj.shipping_full_name,
            "phone": obj.shipping_phone,
            "email": obj.shipping_email,
            "address_line": obj.shipping_address_line,
            "apartment": obj.shipping_apartment,
            "city": obj.shipping_city,
            "state": obj.shipping_state,
            "lga": obj.shipping_lga,
            "postal_code": obj.shipping_postal_code,
            "country": obj.shipping_country,
            "method": obj.shipping_method_name,
            "is_pickup": obj.is_pickup,
            "estimated_days_min": obj.estimated_delivery_days_min,
            "estimated_days_max": obj.estimated_delivery_days_max,
            "delivery_instructions": obj.delivery_instructions,
        }

    def get_payments(self, obj):
        return [
            {"reference": p.reference, "status": p.status, "amount": str(money(p.amount)),
             "verified": p.is_verified, "paid_at": p.paid_at}
            for p in obj.payments.order_by("-created_at")
        ]

    def get_refunds(self, obj):
        return [
            {"refund_number": r.refund_number, "status": r.status,
             "amount_requested": str(money(r.amount_requested)),
             "amount_refunded": str(money(r.amount_refunded)),
             "created_at": r.created_at}
            for r in obj.refunds.order_by("-created_at")
        ]

    def get_tracking(self, obj):
        from apps.shipping.services import ShippingService

        return ShippingService.track(obj)


class StaffOrderSerializer(OrderDetailSerializer):
    customer_email = serializers.CharField(read_only=True)
    customer_name = serializers.CharField(read_only=True)
    internal_note = serializers.CharField(read_only=True)

    class Meta(OrderDetailSerializer.Meta):
        fields = OrderDetailSerializer.Meta.fields + [
            "customer_email", "customer_name", "internal_note", "source_ip",
            "idempotency_key", "stock_committed_at", "updated_at",
        ]
        read_only_fields = fields


class CheckoutSerializer(serializers.Serializer):
    """Shared payload for both cart checkout and Buy Now."""

    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=16)
    address_line = serializers.CharField(max_length=255)
    apartment = serializers.CharField(max_length=120, required=False, allow_blank=True)
    city = serializers.CharField(max_length=80)
    state = serializers.CharField(max_length=80)
    lga = serializers.CharField(max_length=80, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country = serializers.CharField(max_length=80, required=False, default="Nigeria")
    delivery_instructions = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    email = serializers.EmailField(required=False, allow_blank=True)
    customer_note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    shipping_method_code = serializers.CharField(required=False, allow_blank=True)
    promo_codes = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False
    )
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def to_shipping(self) -> dict:
        d = self.validated_data
        return {
            "full_name": d["full_name"],
            "phone": d["phone"],
            "address_line": d["address_line"],
            "apartment": d.get("apartment", ""),
            "city": d["city"],
            "state": d["state"],
            "lga": d.get("lga", ""),
            "postal_code": d.get("postal_code", ""),
            "country": d.get("country", "Nigeria"),
            "delivery_instructions": d.get("delivery_instructions", ""),
        }


class BuyNowSerializer(CheckoutSerializer):
    product_id = serializers.UUIDField()
    variation_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=50, default=1)
    custom_order_details = serializers.JSONField(required=False)
