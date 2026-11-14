from rest_framework import serializers

from .models import Inventory, InventoryMovement


class InventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    variation_sku = serializers.CharField(source="variation.sku", read_only=True, default=None)
    variation_name = serializers.CharField(source="variation.display_name", read_only=True, default=None)
    available = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    effective_threshold = serializers.IntegerField(read_only=True)

    class Meta:
        model = Inventory
        fields = ["id", "product", "product_name", "product_sku", "variation", "variation_sku",
                  "variation_name", "on_hand", "reserved", "available", "low_stock_threshold",
                  "effective_threshold", "is_low_stock", "is_out_of_stock", "updated_at"]


class InventoryMovementSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    performed_by_email = serializers.CharField(source="performed_by.email", read_only=True, default=None)
    order_reference = serializers.CharField(source="order.reference", read_only=True, default=None)

    class Meta:
        model = InventoryMovement
        fields = ["id", "inventory", "product", "product_sku", "variation", "movement_type",
                  "quantity_change", "on_hand_before", "on_hand_after", "reserved_before",
                  "reserved_after", "order", "order_reference", "performed_by_email", "reason", "created_at"]


class StockAdjustSerializer(serializers.Serializer):
    delta = serializers.IntegerField(help_text="Signed quantity change, e.g. -2 or +10.")
    reason = serializers.CharField(max_length=255)

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("Delta cannot be zero.")
        return value


class StockReceiveSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
