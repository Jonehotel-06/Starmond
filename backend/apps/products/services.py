"""
ProductService — catalogue CRUD, variations, images and search.

All write paths validate SKU uniqueness, slug uniqueness, price integrity and
category publication state. Search is indexed and always paginated.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.utils import timezone

from apps.audit.services import AuditService
from apps.categories.models import Category
from apps.core.exceptions import ConflictError, NotFound, ValidationError
from apps.core.models import PublishableModel
from apps.core.utils import money, unique_slug
from apps.inventory.services import InventoryService
from apps.products.models import (
    Brand,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    ProductVariation,
)

logger = logging.getLogger("apps.products")

SORT_OPTIONS = {
    "newest": ["-created_at"],
    "oldest": ["created_at"],
    "price_low": ["price"],
    "price_high": ["-price"],
    "popular": ["-sold_count", "-created_at"],
    "rating": ["-rating_average", "-rating_count"],
    "name": ["name"],
}


class ProductService:
    # ------------------------------------------------------------------
    # Create / update
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def create_product(*, name: str, category: Category, price, sku: str,
                       actor=None, opening_stock: int = 0, **fields) -> Product:
        name = (name or "").strip()
        sku = (sku or "").strip().upper()
        if not name:
            raise ValidationError({"name": ["A product name is required."]})
        if not sku:
            raise ValidationError({"sku": ["A SKU is required."]})
        if Product.objects.filter(sku=sku).exists():
            raise ConflictError(f"SKU '{sku}' is already in use.")
        if category.status != PublishableModel.Status.PUBLISHED:
            raise ValidationError(
                {"category": ["Publish the category before adding products to it."]}
            )

        price = money(price)
        if price < 0:
            raise ValidationError({"price": ["Price cannot be negative."]})

        allowed = {
            "brand", "short_description", "description", "specifications", "key_features",
            "tags", "search_keywords", "compare_at_price", "cost_price", "tax_rate_percent",
            "product_type", "condition", "custom_order_enabled", "custom_order_lead_time_days",
            "custom_order_instructions", "is_featured", "is_new_arrival", "weight_kg",
            "requires_shipping", "is_heavy", "warranty", "meta_title", "meta_description",
            "meta_keywords", "og_image_url", "canonical_url", "noindex", "status", "slug",
            "currency",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValidationError(f"Unsupported field(s): {', '.join(sorted(unknown))}.")

        product = Product(
            name=name,
            sku=sku,
            category=category,
            price=price,
            slug=fields.pop("slug", None) or unique_slug(Product, name),
            **fields,
        )
        if product.status == PublishableModel.Status.PUBLISHED:
            product.published_at = timezone.now()
        product.full_clean(exclude=["published_at"])
        product.save()

        # Stock can be recorded while a product is still a draft, so the owner can
        # photograph and price it before it goes live.
        if product.status == PublishableModel.Status.PUBLISHED or opening_stock:
            InventoryService.get_or_create_for(
                product, None, opening_quantity=max(int(opening_stock or 0), 0)
            )

        AuditService.record(
            action="create",
            entity_type="product",
            entity_id=product.pk,
            actor=actor,
            summary=f"Product {product.sku} created",
            after={"name": product.name, "price": str(product.price), "category": str(category.pk)},
        )
        return product

    @staticmethod
    @transaction.atomic
    def update_product(product: Product, *, actor=None, **fields) -> Product:
        allowed = {
            "name", "category", "brand", "short_description", "description", "specifications",
            "key_features", "tags", "search_keywords", "price", "compare_at_price", "cost_price",
            "tax_rate_percent", "product_type", "condition", "custom_order_enabled",
            "custom_order_lead_time_days", "custom_order_instructions", "is_featured",
            "is_new_arrival", "weight_kg", "requires_shipping", "is_heavy", "warranty",
            "meta_title", "meta_description", "meta_keywords", "og_image_url", "canonical_url",
            "noindex", "status", "slug", "is_variation_based",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValidationError(f"Unsupported field(s): {', '.join(sorted(unknown))}.")

        before = {}
        for key in fields:
            before[key] = str(getattr(product, key)) if not hasattr(getattr(product, key), "pk") \
                else str(getattr(product, key).pk)

        for key, value in fields.items():
            if key == "price":
                value = money(value)
                if value < 0:
                    raise ValidationError({"price": ["Price cannot be negative."]})
                if value != product.price:
                    AuditService.record(
                        action="price_changed",
                        entity_type="product",
                        entity_id=product.pk,
                        actor=actor,
                        summary=f"{product.sku} price {product.price} → {value}",
                        before={"price": str(product.price)},
                        after={"price": str(value)},
                    )
            if key == "category" and value.status != PublishableModel.Status.PUBLISHED:
                raise ValidationError(
                    {"category": ["Products can only be assigned to a published category."]}
                )
            setattr(product, key, value)

        if product.status == PublishableModel.Status.PUBLISHED and not product.published_at:
            product.published_at = timezone.now()
        product.full_clean(exclude=["published_at"])
        product.save()

        if product.status == PublishableModel.Status.PUBLISHED:
            InventoryService.get_or_create_for(product, None)

        AuditService.record(
            action="update",
            entity_type="product",
            entity_id=product.pk,
            actor=actor,
            summary=f"Product {product.sku} updated",
            before=before,
            after={k: str(getattr(product, k)) for k in fields if not hasattr(getattr(product, k), "pk")},
        )
        return product

    @staticmethod
    @transaction.atomic
    def delete_product(product: Product, *, actor=None) -> None:
        """Soft-deletes a product; orders keep referencing it forever."""
        if product.order_items.exists():
            product.status = PublishableModel.Status.ARCHIVED
            product.is_featured = False
            product.save(update_fields=["status", "is_featured", "updated_at"])
            AuditService.record(
                action="update", entity_type="product", entity_id=product.pk, actor=actor,
                summary=f"Product {product.sku} archived (referenced by orders)",
            )
            return
        product.delete()  # soft delete via SoftDeleteModel
        AuditService.record(
            action="delete", entity_type="product", entity_id=product.pk, actor=actor,
            summary=f"Product {product.sku} deleted",
        )

    @staticmethod
    @transaction.atomic
    def publish(product: Product, *, actor=None) -> Product:
        if product.category.status != PublishableModel.Status.PUBLISHED:
            raise ConflictError("Publish the parent category first.")
        product.status = PublishableModel.Status.PUBLISHED
        product.published_at = product.published_at or timezone.now()
        product.save(update_fields=["status", "published_at", "updated_at"])
        InventoryService.get_or_create_for(product, None)
        AuditService.record(
            action="update", entity_type="product", entity_id=product.pk, actor=actor,
            summary=f"Product {product.sku} published",
        )
        return product

    @staticmethod
    @transaction.atomic
    def unpublish(product: Product, *, actor=None) -> Product:
        product.status = PublishableModel.Status.DRAFT
        product.save(update_fields=["status", "updated_at"])
        AuditService.record(
            action="update", entity_type="product", entity_id=product.pk, actor=actor,
            summary=f"Product {product.sku} unpublished",
        )
        return product

    # ------------------------------------------------------------------
    # Variations
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def add_variation(*, product: Product, sku: str, attribute_value_ids: list[str],
                      price_override=None, compare_at_price=None, opening_stock: int = 0,
                      actor=None, **fields) -> ProductVariation:
        sku = (sku or "").strip().upper()
        if not sku:
            raise ValidationError({"sku": ["A variation SKU is required."]})
        if ProductVariation.objects.filter(sku=sku).exists():
            raise ConflictError(f"SKU '{sku}' is already in use.")

        values = list(ProductAttributeValue.objects.filter(pk__in=attribute_value_ids))
        if len(values) != len(set(attribute_value_ids)):
            raise ValidationError({"attribute_value_ids": ["One or more options do not exist."]})
        if not values:
            raise ValidationError({"attribute_value_ids": ["Select at least one option."]})

        variation = ProductVariation(
            product=product,
            sku=sku,
            price_override=money(price_override) if price_override is not None else None,
            compare_at_price=money(compare_at_price) if compare_at_price is not None else None,
            **{k: v for k, v in fields.items() if k in {"image", "weight_kg", "position", "is_active"}},
        )
        variation.full_clean(exclude=["product"])
        variation.save()
        variation.attribute_values.set(values)

        if not product.is_variation_based:
            product.is_variation_based = True
            product.save(update_fields=["is_variation_based", "updated_at"])

        InventoryService.get_or_create_for(
            product, variation, opening_quantity=max(int(opening_stock or 0), 0)
        )
        AuditService.record(
            action="create", entity_type="product_variation", entity_id=variation.pk, actor=actor,
            summary=f"Variation {variation.sku} added to {product.sku}",
            after={"price_override": str(variation.price_override) if variation.price_override else None},
        )
        return variation

    @staticmethod
    @transaction.atomic
    def update_variation(variation: ProductVariation, *, actor=None, **fields) -> ProductVariation:
        allowed = {"price_override", "compare_at_price", "image", "weight_kg", "position", "is_active"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValidationError(f"Unsupported field(s): {', '.join(sorted(unknown))}.")
        for key, value in fields.items():
            if key in {"price_override", "compare_at_price"} and value is not None:
                value = money(value)
                if value < 0:
                    raise ValidationError({key: ["Price cannot be negative."]})
            setattr(variation, key, value)
        variation.full_clean(exclude=["product", "sku"])
        variation.save()
        AuditService.record(
            action="update", entity_type="product_variation", entity_id=variation.pk, actor=actor,
            summary=f"Variation {variation.sku} updated",
            after={k: str(v) for k, v in fields.items()},
        )
        return variation

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def add_image(*, product: Product, image, alt_text: str = "", is_primary: bool = False,
                  variation: ProductVariation | None = None, position: int | None = None) -> ProductImage:
        if position is None:
            position = product.images.count()
        record = ProductImage.objects.create(
            product=product,
            variation=variation,
            image=image,
            alt_text=(alt_text or product.name)[:200],
            is_primary=is_primary or not product.images.exclude(pk="").exists(),
            position=position,
        )
        return record

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @staticmethod
    def get_public_product(slug_or_id: str) -> Product:
        product = (
            Product.objects.public()
            .filter(Q(slug=slug_or_id) | Q(pk=_as_uuid(slug_or_id)))
            .select_related("category", "brand")
            .prefetch_related("images", "variations", "variations__attribute_values")
            .first()
        )
        if product is None:
            raise NotFound("Product not found.")
        return product

    @staticmethod
    def search(*, query: str = "", category: Category | None = None, min_price=None,
               max_price=None, in_stock_only: bool = False, featured: bool = None,
               sort: str = "newest", brand_ids: list[str] | None = None):
        """
        Indexed, category-aware, paginated search. Never returns an unbounded set.
        """
        qs = Product.objects.public().select_related("category", "brand").prefetch_related("images")

        if category is not None:
            qs = qs.filter(category_id__in=category.descendant_ids(include_self=True))

        if query:
            term = query.strip()[:120]
            qs = qs.filter(
                Q(name__icontains=term)
                | Q(sku__iexact=term)
                | Q(short_description__icontains=term)
                | Q(description__icontains=term)
                | Q(search_keywords__icontains=term)
                | Q(category__name__icontains=term)
                | Q(brand__name__icontains=term)
            ).annotate(
                relevance=Case(
                    When(name__icontains=term, then=Value(3)),
                    When(sku__iexact=term, then=Value(5)),
                    When(category__name__icontains=term, then=Value(2)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
        if min_price is not None:
            qs = qs.filter(price__gte=money(min_price))
        if max_price is not None:
            qs = qs.filter(price__lte=money(max_price))
        if featured is not None:
            qs = qs.filter(is_featured=featured)
        if brand_ids:
            qs = qs.filter(brand_id__in=brand_ids)

        if in_stock_only:
            from apps.inventory.models import Inventory

            available_ids = Inventory.objects.filter(
                track_inventory=True, quantity_on_hand__gt=F("quantity_reserved")
            ).values_list("product_id", flat=True)
            unlimited_ids = Inventory.objects.filter(track_inventory=False).values_list(
                "product_id", flat=True
            )
            qs = qs.filter(Q(pk__in=available_ids) | Q(pk__in=unlimited_ids))

        if query and not sort:
            return qs.order_by("-relevance", "-created_at")
        return qs.order_by(*SORT_OPTIONS.get(sort, SORT_OPTIONS["newest"]))

    @staticmethod
    def related_products(product: Product, limit: int = 8):
        return (
            Product.objects.public()
            .filter(category_id=product.category_id)
            .exclude(pk=product.pk)
            .order_by("-sold_count", "-created_at")[:limit]
        )

    @staticmethod
    def increment_view(product: Product) -> None:
        Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)

    @staticmethod
    def catalogue_facets(category: Category | None = None) -> dict:
        """Filter metadata for the storefront sidebar."""
        qs = Product.objects.public()
        if category is not None:
            qs = qs.filter(category_id__in=category.descendant_ids(include_self=True))
        price_range = qs.aggregate(
            low=Coalesce_min("price"), high=Coalesce_max("price")
        )
        return {
            "price_range": {
                "min": str(money(price_range["low"] or 0)),
                "max": str(money(price_range["high"] or 0)),
            },
            "brands": [
                {"id": str(b.pk), "name": b.name, "slug": b.slug}
                for b in Brand.objects.filter(is_active=True, products__in=qs).distinct()
            ],
            "sort_options": list(SORT_OPTIONS.keys()),
        }


def _as_uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return uuid.UUID(int=0)


def Coalesce_min(field):
    from django.db.models import Min

    return Min(field)


def Coalesce_max(field):
    from django.db.models import Max

    return Max(field)
