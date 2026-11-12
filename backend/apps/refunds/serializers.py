from decimal import Decimal

from rest_framework import serializers

from apps.core.utils import money
from apps.refunds.models import Refund, RefundItem


class RefundItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="order_item.product_name", read_only=True)
    sku = serializers.CharField(source="order_item.sku", read_only=True)

    class Meta:
        model = RefundItem
        fields = ["id", "order_item", "product_name", "sku", "quantity", "amount"]


class RefundSerializer(serializers.ModelSerializer):
    items = RefundItemSerializer(many=True, read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reason_label = serializers.CharField(source="get_reason_category_display", read_only=True)

    class Meta:
        model = Refund
        fields = ["id", "refund_number", "order_number", "refund_type", "status", "status_label",
                  "reason_category", "reason_label", "customer_note", "amount_requested",
                  "amount_approved", "amount_refunded", "currency", "provider_status",
                  "items", "created_at", "reviewed_at", "completed_at", "restock_processed"]


class RefundRequestSerializer(serializers.Serializer):
    order_number = serializers.CharField(max_length=32)
    reason_category = serializers.ChoiceField(choices=Refund.Reason.choices)
    customer_note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    items = serializers.ListField(child=serializers.DictField(), required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=Decimal("0"))


class RefundDecisionSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=Decimal("0"))
    restock = serializers.BooleanField(default=False)
    note = serializers.CharField(required=False, allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True)
