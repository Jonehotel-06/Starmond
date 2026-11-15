from rest_framework import serializers

from .models import Order, OrderItem, OrderStatusLog


class OrderItemSerializer(serializers.ModelSerializer):
    variation_options = serializers.JSONField(source="variation.options", read_only=True, default=None)
    product_slug = serializers.CharField(source="product.slug", read_only=True, default=None)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "product_slug", "sku", "variation", "variation_label",
                  "variation_options", "unit_price", "quantity", "line_total", "customization",
                  "reference_image"]


class OrderStatusLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = OrderStatusLog
        fields = ["from_status", "to_status", "actor_email", "note", "created_at"]


class OrderSummarySerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["reference", "status", "payment_status", "currency", "subtotal_amount",
                  "discount_amount", "shipping_fee", "total_amount", "item_count",
                  "shipping_method_name", "delivery_state", "placed_at", "paid_at"]

    def get_item_count(self, obj):
        return sum(i.quantity for i in obj.items.all())


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    delivery = serializers.SerializerMethodField()
    contact = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    fulfilment = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["reference", "status", "payment_status", "source", "currency", "items",
                  "delivery", "contact", "totals", "fulfilment", "promotion_code_snapshot",
                  "placed_at", "paid_at", "shipped_at", "delivered_at", "completed_at",
                  "cancelled_at", "expires_at"]

    def get_delivery(self, obj):
        return {
            "full_name": obj.delivery_full_name, "phone": obj.delivery_phone,
            "state": obj.delivery_state, "city": obj.delivery_city, "street": obj.delivery_street,
            "details": obj.delivery_details, "instructions": obj.delivery_instructions,
            "method": obj.shipping_method_name, "method_kind": obj.shipping_method_kind,
            "estimate": obj.shipping_estimate, "tracking_reference": obj.tracking_reference,
            "notes": obj.delivery_notes,
        }

    def get_contact(self, obj):
        return {"full_name": obj.contact_full_name, "email": obj.contact_email, "phone": obj.contact_phone}

    def get_totals(self, obj):
        return {
            "subtotal": str(obj.subtotal_amount), "discount": str(obj.discount_amount),
            "shipping_fee": str(obj.shipping_fee), "total": str(obj.total_amount),
            "refunded": str(obj.total_refunded), "currency": obj.currency,
        }

    def get_fulfilment(self, obj):
        return {"status": obj.status, "tracking_reference": obj.tracking_reference,
                "delivered_at": obj.delivered_at, "shipped_at": obj.shipped_at}


class OrderStaffSerializer(OrderDetailSerializer):
    customer_email = serializers.CharField(source="customer.email", read_only=True, default=None)
    status_history = OrderStatusLogSerializer(source="status_logs", many=True, read_only=True)
    internal_notes = serializers.CharField(read_only=True)
    payments = serializers.SerializerMethodField()

    class Meta(OrderDetailSerializer.Meta):
        fields = OrderDetailSerializer.Meta.fields + [
            "id", "customer", "customer_email", "internal_notes", "status_history", "payments"]

    def get_payments(self, obj):
        return [
            {"reference": p.reference, "provider_reference": p.provider_reference, "amount": str(p.amount),
             "status": p.status, "channel": p.channel, "initialized_at": p.initialized_at,
             "verified_at": p.verified_at, "failure_reason": p.failure_reason}
            for p in obj.payments.all()
        ]


class CheckoutSerializer(serializers.Serializer):
    contact = serializers.DictField(required=False, default=dict,
        help_text='Guest: {"full_name","email","phone"}. Ignored for authenticated customers.')
    delivery = serializers.DictField(
        help_text='{"full_name","phone","state","city","street","details","instructions","shipping_method_id"}')
    source = serializers.DictField(required=False, default=dict,
        help_text='{"type":"cart","cart_token":...} or {"type":"buy_now","product_id":..,"variation_id":..,"quantity":..,"customization":{}}')
    promotion_code = serializers.CharField(required=False, allow_blank=True, max_length=40)
    cart_token = serializers.CharField(required=False, allow_blank=True, max_length=64)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=80)

    def validate_source(self, value):
        stype = value.get("type", "cart")
        if stype not in ("cart", "buy_now"):
            raise serializers.ValidationError('source.type must be "cart" or "buy_now".')
        if stype == "buy_now" and not value.get("product_id"):
            raise serializers.ValidationError("source.product_id is required for Buy Now.")
        value["type"] = stype
        return value


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    tracking_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)


class GuestLookupSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=32)
    email = serializers.EmailField()
