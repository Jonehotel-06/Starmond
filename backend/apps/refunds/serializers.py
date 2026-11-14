from rest_framework import serializers

from .models import Refund


class RefundSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    payment_reference = serializers.CharField(source="payment.reference", read_only=True)
    processed_by_email = serializers.CharField(source="processed_by.email", read_only=True, default=None)

    class Meta:
        model = Refund
        fields = ["id", "reference", "order", "order_reference", "payment_reference", "reason",
                  "requested_amount", "approved_amount", "status", "restock_items",
                  "provider_refund_id", "processed_by_email", "decided_at", "processed_at",
                  "created_at"]
        read_only_fields = ["id", "reference", "approved_amount", "status", "provider_refund_id",
                            "processed_by_email", "decided_at", "processed_at", "created_at"]


class RefundRequestSerializer(serializers.Serializer):
    order_reference = serializers.CharField(max_length=32)
    reason = serializers.CharField(max_length=2000)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    restock = serializers.BooleanField(required=False, default=False)


class RefundDecisionSerializer(serializers.Serializer):
    approved_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
