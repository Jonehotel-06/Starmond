import hashlib
import json

from django.db import models

from apps.core.models import TimeStampedModel


class ProductQuerySet(models.QuerySet):
    def public(self):
        """Only products customers may see."""
        return self.filter(status=Product.Status.ACTIVE, is_active=True)


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        OUT_OF_STOCK = "out_of_stock", "Out of stock"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=64, unique=True, db_index=True)
    slug = models.SlugField(max_length=220, unique=True, db_index=True)
    category = models.ForeignKey("categories.Category", on_delete=models.PROTECT, related_name="products")
    short_description = models.CharField(max_length=400, blank=True)
    description = models.TextField(blank=True)
    # Pricing — cost_price is PRIVATE (never serialized to public/staff-low APIs)
    regular_price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="NGN")
    # Inventory defaults (variation-level stock lives in inventory.Inventory)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    # Flags & status
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_new_arrival = models.BooleanField(default=False, db_index=True)
    is_best_seller = models.BooleanField(default=False, db_index=True)
    # Physical
    weight_kg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    length_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    brand = models.CharField(max_length=120, blank=True, db_index=True)
    tags = models.CharField(max_length=255, blank=True, help_text="Comma-separated tags.")
    specifications = models.JSONField(default=dict, blank=True)
    video_url = models.URLField(max_length=400, blank=True)
    # Made-to-order (custom fashion) support
    supports_customization = models.BooleanField(default=False)
    customization_schema = models.JSONField(default=list, blank=True,
        help_text='e.g. [{"field":"size","label":"Clothing size","type":"select","required":true,"options":["S","M","L"]}]')
    # SEO
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    seo_keywords = models.CharField(max_length=255, blank=True)
    canonical_url = models.URLField(max_length=300, blank=True)
    og_image = models.ImageField(upload_to="products/og/", blank=True, null=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        db_table = "products_product"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "is_active", "-created_at"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    # ------------------------------------------------------------- pricing
    @property
    def on_sale(self):
        return self.sale_price is not None and self.sale_price < self.regular_price

    @property
    def effective_price(self):
        return self.sale_price if self.on_sale else self.regular_price

    # ------------------------------------------------------------- catalogue
    @property
    def is_public(self):
        return self.status == self.Status.ACTIVE and self.is_active

    @property
    def main_image(self):
        """First image from the (prefetch-cached) ordered image list.
        images.all() honours prefetch_related; .filter() would NOT and causes N+1."""
        images = list(self.images.all())
        return images[0] if images else None

    @property
    def has_variations(self):
        return self.variations.exists()

    @property
    def url_path(self):
        """Public URL e.g. /shop/electrical/cables/copper-cable-2-5mm/"""
        return f"{self.category.url_path}{self.slug}/"

    def stock_summary(self):
        """Authoritative stock via the inventory app (never stored twice)."""
        from apps.inventory.services import InventoryService
        return InventoryService.product_summary(self)

    @property
    def is_in_stock(self):
        return self.stock_summary()["available"] > 0

    def effective_seo(self):
        image = self.main_image
        return {
            "title": self.seo_title or f"{self.name} | STARMOND TECHNOLOGY LIMITED",
            "description": self.seo_description or self.short_description or (self.description[:300] if self.description else ""),
            "keywords": self.seo_keywords or self.tags,
            "canonical_url": self.canonical_url,
            "og_image": self.og_image.url if self.og_image else (image.file_url if image else None),
        }

    def tag_list(self):
        return [t.strip().lower() for t in self.tags.split(",") if t.strip()]


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    file = models.ImageField(upload_to="products/images/")
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_main = models.BooleanField(default=False)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "products_image"
        ordering = ["-is_main", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "is_main"], name="one_main_image_per_product",
                                      condition=models.Q(is_main=True)),
        ]

    @property
    def file_url(self):
        return self.file.url if self.file else None

    def thumbnail_url(self):
        from apps.media.services import MediaService
        key = getattr(self, "_thumb_key", None)
        if key:
            return MediaService.public_url(key) if hasattr(MediaService, "public_url") else None
        return self.file_url


class ProductAttribute(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=80, help_text="e.g. Size, Colour, Cable length, Voltage")
    is_variation_attribute = models.BooleanField(default=False,
        help_text="Attributes flagged here drive selectable variations.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "products_attribute"
        ordering = ["sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=["product", "name"], name="unique_attribute_per_product")]


class ProductAttributeValue(TimeStampedModel):
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "products_attribute_value"
        ordering = ["sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=["attribute", "value"], name="unique_value_per_attribute")]


class ProductVariation(TimeStampedModel):
    """Sellable variation with independent SKU, pricing and stock."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variations")
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=160, blank=True, help_text="Display label, e.g. 'XL / Red'")
    options = models.JSONField(default=dict, help_text='Selected attribute values, e.g. {"Size": "XL", "Colour": "Red"}')
    options_hash = models.CharField(max_length=40, blank=True, db_index=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                help_text="Absolute price override (takes precedence).")
    price_adjustment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                           help_text="Added to the product's effective price.")
    is_available = models.BooleanField(default=True)
    image = models.ForeignKey(ProductImage, on_delete=models.SET_NULL, null=True, blank=True, related_name="variations")

    class Meta:
        db_table = "products_variation"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["product", "options_hash"], name="unique_variation_options")]

    def __str__(self):
        return f"{self.product.sku}::{self.sku}"

    def save(self, *args, **kwargs):
        self.options_hash = hashlib.sha1(
            json.dumps(self.options or {}, sort_keys=True).encode()
        ).hexdigest()
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        base = self.product.effective_price
        if self.price is not None:
            return self.price
        if self.price_adjustment is not None:
            return base + self.price_adjustment
        return base

    @property
    def display_name(self):
        return self.name or " / ".join(str(v) for v in (self.options or {}).values()) or self.sku
