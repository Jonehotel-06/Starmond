from rest_framework import serializers

from .models import Promotion


class PromotionSerializer(serializers.ModelSerializer):
    banner_image_url = serializers.CharField(read_only=True)
    total_usages = serializers.IntegerField(read_only=True)
    is_within_window = serializers.BooleanField(read_only=True)

    class Meta:
        model = Promotion
        fields = ["id", "code", "name", "description", "kind", "value", "scope", "product_ids",
                  "category_ids", "min_purchase_amount", "max_discount_amount", "starts_at", "ends_at",
                  "usage_limit", "usage_limit_per_customer", "applies_to_sale_items",
                  "first_time_customers_only", "is_active", "banner_image", "banner_image_url",
                  "total_usages", "is_within_window", "created_at"]
        read_only_fields = ["id", "created_at", "total_usages"]

    def validate(self, attrs):
        code = (attrs.get("code") or getattr(self.instance, "code") or "").strip().upper()
        attrs["code"] = code
        if Promotion.objects.filter(code=code).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError({"code": "This code already exists."})
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        value = attrs.get("value", getattr(self.instance, "value", None))
        if kind == "percentage" and value is not None and (value <= 0 or value > 100):
            raise serializers.ValidationError({"value": "Percentage must be between 0 and 100."})
        if attrs.get("ends_at") and attrs.get("starts_at") and attrs["ends_at"] <= attrs["starts_at"]:
            raise serializers.ValidationError({"ends_at": "End must be after start."})
        return attrs


class PromotionValidateRequestSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40)
    items = serializers.ListField(
        child=serializers.DictField(), required=False,
        help_text='[{"product_id": 1, "variation_id": null, "quantity": 2}]')
