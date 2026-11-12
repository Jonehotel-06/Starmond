"""Public catalogue serializers. Internal fields (cost price) never appear."""
from __future__ import annotations

from rest_framework import serializers

from apps.products.models import (
    Brand, Product, ProductAttribute, ProductAttributeValue, ProductImage, ProductVariation,
)
from apps.inventory.services import InventoryService


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "url", "alt_text", "position", "is_primary", "variation"]

    def get_url(self, obj) -> str | None:
        try:
            return obj.image.url
        except ValueError:
            return None


class VariationSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()
    label = serializers.CharField(read_only=True)
    available_quantity = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    attributes = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariation
        fields = ["id", "sku", "label", "price", "compare_at_price", "attributes",
                  "available_quantity", "stock_status", "image", "is_active"]

    def get_price(self, obj):
        return str(obj.effective_price)

    def get_attributes(self, obj):
        return [
            {"attribute": v.attribute.name, "slug": v.attribute.slug,
             "value": v.value, "color_hex": v.color_hex}
            for v in obj.attribute_values.select_related("attribute")
        ]

    def get_available_quantity(self, obj):
        return InventoryService.available_quantity(obj.product, obj)

    def get_stock_status(self, obj):
        return InventoryService.stock_status_for(obj.product, obj)

    def get_image(self, obj):
        try:
            return obj.image.url if obj.image else None
        except ValueError:
            return None


class ProductListSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()
    compare_at_price = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    url = serializers.CharField(source="absolute_path", read_only=True)
    on_sale = serializers.BooleanField(read_only=True)
    discount_percentage = serializers.IntegerField(read_only=True)
    stock_status = serializers.SerializerMethodField()
    has_variations = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "slug", "sku", "url", "price", "compare_at_price",
                  "on_sale", "discount_percentage", "primary_image", "category",
                  "short_description", "rating_average", "rating_count", "sold_count",
                  "is_featured", "is_new_arrival", "stock_status", "has_variations",
                  "custom_order_enabled", "created_at"]

    def get_price(self, obj):
        return str(obj.price)

    def get_compare_at_price(self, obj):
        return str(obj.compare_at_price) if obj.compare_at_price else None

    def get_primary_image(self, obj):
        image = obj.primary_image
        try:
            return image.image.url if image else None
        except ValueError:
            return None

    def get_category(self, obj):
        return {"id": str(obj.category_id), "name": obj.category.name,
                "slug": obj.category.slug, "url": obj.category.absolute_path} if obj.category_id else None

    def get_stock_status(self, obj):
        return InventoryService.stock_status_for(obj)

    def get_has_variations(self, obj):
        return bool(obj.is_variation_based or obj.variations.exists())


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variations = serializers.SerializerMethodField()
    attributes = serializers.SerializerMethodField()
    related_products = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    seo = serializers.SerializerMethodField()
    breadcrumbs = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description", "specifications", "key_features", "tags", "brand",
            "condition", "product_type", "warranty", "weight_kg",
            "custom_order_instructions", "custom_order_lead_time_days",
            "images", "variations", "attributes", "related_products", "availability",
            "seo", "breadcrumbs", "updated_at",
        ]

    def get_variations(self, obj):
        active = obj.variations.filter(is_active=True).prefetch_related(
            "attribute_values", "attribute_values__attribute"
        )
        return VariationSerializer(active, many=True, context=self.context).data

    def get_attributes(self, obj):
        rows = {}
        for value in obj.attribute_values.select_related("attribute"):
            rows.setdefault(value.attribute.name, []).append(
                {"value": value.value, "slug": value.slug, "color_hex": value.color_hex}
            )
        return [{"name": name, "values": values} for name, values in rows.items()]

    def get_related_products(self, obj):
        from apps.products.services import ProductService

        return ProductListSerializer(
            ProductService.related_products(obj), many=True, context=self.context
        ).data

    def get_availability(self, obj):
        return {
            "stock_status": InventoryService.stock_status_for(obj),
            "available_quantity": InventoryService.available_quantity(obj),
            "requires_shipping": obj.requires_shipping,
        }

    def get_seo(self, obj):
        from apps.seo.services import SEOService

        return SEOService.product_metadata(obj)

    def get_breadcrumbs(self, obj):
        from apps.seo.services import SEOService

        return SEOService._product_breadcrumbs(obj)


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "logo", "description"]


class AttributeValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttributeValue
        fields = ["id", "value", "slug", "color_hex"]


class AttributeSerializer(serializers.ModelSerializer):
    values = AttributeValueSerializer(many=True, read_only=True)

    class Meta:
        model = ProductAttribute
        fields = ["id", "name", "slug", "input_type", "is_variation_axis", "values"]
