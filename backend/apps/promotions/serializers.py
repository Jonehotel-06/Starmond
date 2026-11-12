from rest_framework import serializers

from apps.promotions.models import Promotion


class PromotionSerializer(serializers.ModelSerializer):
    remaining_uses = serializers.IntegerField(read_only=True)

    class Meta:
        model = Promotion
        fields = ["id", "name", "code", "description", "promotion_type", "value",
                  "max_discount_amount", "min_order_amount", "applies_to", "starts_at",
                  "ends_at", "usage_limit_total", "usage_limit_per_customer",
                  "first_order_only", "is_active", "is_stackable", "public_label",
                  "remaining_uses", "is_live"]
        read_only_fields = ["id", "remaining_uses", "is_live"]


class PromotionValidateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40)
