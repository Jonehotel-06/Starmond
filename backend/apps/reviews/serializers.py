from rest_framework import serializers

from apps.products.models import Product

from .models import Review


class ReviewPublicSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "rating", "title", "body", "customer_name", "is_verified_purchase", "created_at"]

    def get_customer_name(self, obj):
        if not obj.customer:
            return "Starmond Customer"
        name = obj.customer.full_name.strip()
        if not name:
            return "Starmond Customer"
        parts = name.split()
        return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else f"{parts[0][0]}."


class ReviewCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    body = serializers.CharField(max_length=4000)


class ReviewStaffSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    customer_email = serializers.CharField(source="customer.email", read_only=True, default=None)
    order_reference = serializers.CharField(source="order.reference", read_only=True, default=None)

    class Meta:
        model = Review
        fields = ["id", "product", "product_name", "customer_email", "order_reference", "rating",
                  "title", "body", "is_verified_purchase", "moderation_status", "moderator_note",
                  "created_at"]
