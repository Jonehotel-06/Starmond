from rest_framework import serializers

from apps.customers.models import Address, WishlistItem


class AddressSerializer(serializers.ModelSerializer):
    one_line = serializers.CharField(read_only=True)

    class Meta:
        model = Address
        fields = ["id", "label", "recipient_name", "phone", "email", "street_address",
                  "apartment", "city", "state", "lga", "postal_code", "country",
                  "delivery_instructions", "is_default", "one_line", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_state(self, value):
        from apps.shipping.services import ShippingService

        normalised = ShippingService.normalise_state(value)
        if not normalised:
            raise serializers.ValidationError("Enter a valid state.")
        return normalised


class WishlistItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    price = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    variation_label = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = WishlistItem
        fields = ["id", "product", "product_name", "product_slug", "variation",
                  "variation_label", "price", "image", "in_stock", "created_at"]

    def get_price(self, obj):
        return str(obj.variation.effective_price if obj.variation_id else obj.product.price)

    def get_image(self, obj):
        try:
            image = obj.product.primary_image
            return image.image.url if image else None
        except Exception:
            return None

    def get_variation_label(self, obj):
        return obj.variation.label if obj.variation_id else ""

    def get_in_stock(self, obj):
        from apps.inventory.services import InventoryService

        return InventoryService.available_quantity(obj.product, obj.variation) > 0
