from django.db import transaction

from apps.core.exceptions import ServiceError
from apps.core.slugs import unique_slugify

from .models import Product, ProductImage, ProductVariation


class ProductService:
    @staticmethod
    @transaction.atomic
    def create_or_update(product, data):
        """Validate SKU/slug uniqueness and price sanity, then persist."""
        sku = data.get("sku") or getattr(product, "sku", None)
        if not sku:
            raise ServiceError("SKU is required.", code="sku_required")
        if Product.objects.filter(sku=sku).exclude(pk=getattr(product, "pk", None)).exists():
            raise ServiceError("A product with this SKU already exists.", code="duplicate_sku", status_code=409)
        name = data.get("name", getattr(product, "name", ""))
        slug = data.get("slug") or None
        if slug and Product.objects.filter(slug=slug).exclude(pk=getattr(product, "pk", None)).exists():
            raise ServiceError("A product with this slug already exists.", code="duplicate_slug", status_code=409)
        if not slug and not getattr(product, "slug", None):
            slug = unique_slugify(product, name, queryset=Product.objects.all())
        regular = data.get("regular_price", getattr(product, "regular_price", None))
        sale = data.get("sale_price", getattr(product, "sale_price", None))
        if regular is not None and sale is not None and sale >= regular:
            raise ServiceError("Sale price must be lower than the regular price.", code="invalid_sale_price")
        from apps.categories.models import Category
        for field, value in data.items():
            if field == "slug":
                continue
            if field == "category":
                if not isinstance(value, Category):
                    category = Category.objects.filter(pk=value).first()
                    if not category:
                        raise ServiceError("Category not found.", code="category_not_found")
                    if not category.is_active:
                        raise ServiceError("Cannot assign a product to an inactive category.",
                                           code="inactive_category")
                    value = category
            setattr(product, field, value)
        if slug:
            product.slug = slug
        product.sku = sku
        product.save()
        return product

    @staticmethod
    @transaction.atomic
    def safe_delete(product):
        """Products with order history are ARCHIVED, never hard-deleted, so
        financial records stay intact."""
        from apps.orders.models import OrderItem
        if OrderItem.objects.filter(product=product).exists():
            product.status = Product.Status.ARCHIVED
            product.is_active = False
            product.save(update_fields=["status", "is_active", "updated_at"])
            return "archived"
        product.delete()
        return "deleted"

    @staticmethod
    @transaction.atomic
    def set_main_image(product, image):
        if image.product_id != product.pk:
            raise ServiceError("Image does not belong to this product.", code="image_mismatch")
        ProductImage.objects.filter(product=product, is_main=True).update(is_main=False)
        image.is_main = True
        image.save(update_fields=["is_main", "updated_at"])
        return image

    @staticmethod
    @transaction.atomic
    def reorder_images(product, image_ids):
        for order, image_id in enumerate(image_ids):
            ProductImage.objects.filter(pk=image_id, product=product).update(sort_order=order)

    @staticmethod
    @transaction.atomic
    def upsert_variation(product, data):
        sku = data.get("sku")
        if not sku:
            raise ServiceError("Variation SKU is required.", code="sku_required")
        if Product.objects.filter(sku=sku).exclude(pk=product.pk).exists() or \
           ProductVariation.objects.filter(sku=sku).exclude(product=product, **({"pk": data["id"]} if data.get("id") else {})).exists():
            raise ServiceError("Variation SKU already in use.", code="duplicate_sku", status_code=409)
        variation = ProductVariation.objects.filter(pk=data.get("id")).first() if data.get("id") else None
        if variation and variation.product_id != product.pk:
            raise ServiceError("Variation belongs to another product.", code="variation_mismatch")
        if variation is None:
            variation = ProductVariation(product=product)
        from decimal import Decimal, InvalidOperation
        for field in ("sku", "name", "options", "price", "price_adjustment", "is_available", "image"):
            if field in data:
                value = data[field]
                if field in ("price", "price_adjustment") and value not in (None, ""):
                    try:
                        value = Decimal(str(value))
                    except InvalidOperation:
                        raise ServiceError(f"Invalid decimal for {field}.", code="invalid_price")
                elif field in ("price", "price_adjustment"):
                    value = None
                setattr(variation, field, value)
        if variation.price is not None and variation.price_adjustment is not None:
            raise ServiceError("Provide either an absolute price or a price adjustment, not both.", code="pricing_conflict")
        variation.save()
        from apps.inventory.services import InventoryService
        InventoryService.ensure_inventory(product, variation, opening=data.get("stock_quantity"))
        return variation
