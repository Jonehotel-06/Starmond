from rest_framework import serializers

from apps.products.models import Product, ProductVariation

from .models import CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    variation_label = serializers.CharField(source="variation.display_name", read_only=True, default=None)
    variation_options = serializers.JSONField(source="variation.options", read_only=True, default=None)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_name", "product_slug", "variation", "variation_label",
                  "variation_options", "quantity", "unit_price", "line_total", "image_url"]
        read_only_fields = ["id", "unit_price", "line_total"]

    def get_image_url(self, obj):
        if obj.variation and obj.variation.image:
            return obj.variation.image.file_url
        image = obj.product.main_image
        return image.file_url if image else None


class CartAddSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    variation = serializers.PrimaryKeyRelatedField(queryset=ProductVariation.objects.all(), required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=1000, default=1)

    def validate(self, attrs):
        product, variation = attrs["product"], attrs.get("variation")
        if not product.is_public:
            raise serializers.ValidationError({"product": "This product is not available for purchase."})
        if variation and variation.product_id != product.pk:
            raise serializers.ValidationError({"variation": "Variation does not belong to this product."})
        if variation and not variation.is_available:
            raise serializers.ValidationError({"variation": "This variation is no longer available."})
        if product.has_variations and not variation:
            # Allow adding base product only when variations don't track stock/price individually
            pass
        return attrs


class CartUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=1000)


class CartMergeSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64, help_text="Guest cart token to merge into the authenticated cart.")
