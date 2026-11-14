from decimal import Decimal

from django.db.models import Avg, Count
from rest_framework import serializers

from apps.core.permissions import user_has_permission
from apps.core.constants import Perm

from .models import Product, ProductAttribute, ProductAttributeValue, ProductImage, ProductVariation


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.CharField(source="file_url", read_only=True)

    class Meta:
        model = ProductImage
        fields = ["id", "url", "alt_text", "sort_order", "is_main", "width", "height"]
        read_only_fields = ["id", "url", "width", "height"]


class ProductVariationPublicSerializer(serializers.ModelSerializer):
    effective_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    display_name = serializers.CharField(read_only=True)
    in_stock = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariation
        fields = ["id", "sku", "display_name", "options", "effective_price", "is_available", "in_stock", "image_url"]

    def get_in_stock(self, obj):
        record = getattr(obj, "inventory_record", None)
        return bool(record and record.available > 0) if record is not None else False

    def get_image_url(self, obj):
        return obj.image.file_url if obj.image else None


class ProductVariationStaffSerializer(serializers.ModelSerializer):
    effective_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariation
        fields = ["id", "sku", "name", "display_name", "options", "price", "price_adjustment",
                  "effective_price", "is_available", "image", "stock"]

    def get_stock(self, obj):
        record = getattr(obj, "inventory_record", None)
        if record is None:
            return {"on_hand": 0, "reserved": 0, "available": 0}
        return {"on_hand": record.on_hand, "reserved": record.reserved, "available": record.available}


class AttributeValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttributeValue
        fields = ["id", "value", "sort_order"]


class ProductAttributeSerializer(serializers.ModelSerializer):
    values = AttributeValueSerializer(many=True, read_only=True)

    class Meta:
        model = ProductAttribute
        fields = ["id", "name", "is_variation_attribute", "sort_order", "values"]


class _BaseProductFields(serializers.ModelSerializer):
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    effective_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    on_sale = serializers.BooleanField(read_only=True)
    main_image_url = serializers.SerializerMethodField()
    url_path = serializers.CharField(read_only=True)
    in_stock = serializers.SerializerMethodField()
    rating_summary = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "slug", "sku", "category", "category_slug", "category_name",
                  "short_description", "regular_price", "sale_price", "effective_price", "on_sale",
                  "currency", "main_image_url", "url_path", "is_featured", "is_new_arrival",
                  "is_best_seller", "brand", "in_stock", "rating_summary"]

    def get_main_image_url(self, obj):
        image = obj.main_image
        return image.file_url if image else None

    def get_in_stock(self, obj):
        annotated = getattr(obj, "annotated_available", "missing")
        if annotated != "missing":
            return bool(annotated and annotated > 0)
        return obj.is_in_stock

    def get_rating_summary(self, obj):
        avg = getattr(obj, "avg_rating", None)
        count = getattr(obj, "review_count", None)
        if count is None:
            stats = obj.reviews.approved().aggregate(avg=Avg("rating"), count=Count("id"))
            avg, count = stats["avg"], stats["count"]
        return {"average": round(float(avg), 2) if avg else None, "count": count or 0}


class ProductPublicDetailSerializer(_BaseProductFields):
    images = ProductImageSerializer(many=True, read_only=True)
    variations = serializers.SerializerMethodField()
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    seo = serializers.SerializerMethodField()
    breadcrumb = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()

    class Meta(_BaseProductFields.Meta):
        fields = _BaseProductFields.Meta.fields + [
            "description", "specifications", "tags", "weight_kg", "video_url",
            "images", "variations", "attributes", "seo", "breadcrumb", "stock",
            "supports_customization", "customization_schema", "status", "created_at",
        ]

    def get_variations(self, obj):
        variations = obj.variations.select_related("image").prefetch_related("inventory_record").all()
        return ProductVariationPublicSerializer(variations, many=True).data

    def get_seo(self, obj):
        return obj.effective_seo()

    def get_breadcrumb(self, obj):
        return obj.category.breadcrumb + [{"name": obj.name, "slug": obj.slug, "url_path": obj.url_path}]

    def get_stock(self, obj):
        summary = obj.stock_summary()
        # Customers only see availability signals, not exact stock counts.
        return {
            "in_stock": summary["available"] > 0,
            "low_stock": 0 < summary["available"] <= obj.low_stock_threshold,
        }


class ProductStaffSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    effective_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variations = ProductVariationStaffSerializer(many=True, read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    stock = serializers.SerializerMethodField()
    url_path = serializers.CharField(read_only=True)
    cost_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "sku", "slug", "category", "category_name", "short_description",
                  "description", "regular_price", "sale_price", "effective_price", "cost_price", "currency", "status",
                  "is_active", "is_featured", "is_new_arrival", "is_best_seller", "low_stock_threshold",
                  "weight_kg", "length_cm", "width_cm", "height_cm", "brand", "tags",
                  "specifications", "video_url", "supports_customization", "customization_schema",
                  "seo_title", "seo_description", "seo_keywords", "canonical_url", "og_image",
                  "images", "variations", "attributes", "stock", "url_path", "created_at", "updated_at"]
        read_only_fields = ["id", "slug", "created_at", "updated_at", "url_path"]

    def get_stock(self, obj):
        return obj.stock_summary()

    def get_cost_price(self, obj):
        """Cost price is exposed ONLY to staff holding the finance.view permission."""
        request = self.context.get("request")
        if request and user_has_permission(request.user, Perm.FINANCE_VIEW):
            return obj.cost_price
        return None

    def validate(self, attrs):
        sale = attrs.get("sale_price", getattr(self.instance, "sale_price", None))
        regular = attrs.get("regular_price", getattr(self.instance, "regular_price", None))
        if sale is not None and regular is not None and sale >= regular:
            raise serializers.ValidationError({"sale_price": "Sale price must be lower than the regular price."})
        if attrs.get("regular_price") is not None and attrs["regular_price"] < Decimal("0"):
            raise serializers.ValidationError({"regular_price": "Price cannot be negative."})
        schema = attrs.get("customization_schema")
        if schema is not None and not isinstance(schema, list):
            raise serializers.ValidationError({"customization_schema": "Must be a list of field definitions."})
        return attrs
