"""
Product catalogue: products, galleries, attributes, variations.

Pricing rule (Section 45 rule 15): a product's effective price always comes from
its variation when one is selected, and every price is stored on the server.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, PublishableModel, SoftDeleteModel
from apps.core.utils import unique_slug


class ProductQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def public(self):
        return self.filter(status=PublishableModel.Status.PUBLISHED, deleted_at__isnull=True)

    def with_relations(self):
        return self.select_related("category", "brand").prefetch_related(
            "images", "variations", "attribute_values", "attribute_values__attribute"
        )

    def in_category_tree(self, category):
        return self.filter(category_id__in=category.descendant_ids(include_self=True))

    def featured(self):
        return self.public().filter(is_featured=True)

    def new_arrivals(self):
        return self.public().filter(is_new_arrival=True).order_by("-created_at")

    def best_sellers(self):
        return self.public().order_by("-sold_count", "-created_at")


class ProductManager(models.Manager.from_queryset(ProductQuerySet)):
    """Soft-deleted products stay in the database but disappear from the API."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def public(self):
        return self.get_queryset().public()


class Brand(BaseModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    logo = models.ImageField(upload_to="brands/", null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "products_brand"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(Brand, self.name)
        super().save(*a, **kw)


class ProductAttribute(BaseModel):
    """
    An attribute that either describes a product (e.g. Material) or drives
    variations (e.g. Size, Colour).
    """

    class InputType(models.TextChoices):
        SELECT = "select", "Select"
        RADIO = "radio", "Radio"
        COLOR = "color", "Colour swatch"
        TEXT = "text", "Text"

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    input_type = models.CharField(max_length=20, choices=InputType.choices, default=InputType.SELECT)
    is_variation_axis = models.BooleanField(
        default=False, help_text="When true, this attribute creates product variations."
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "products_attribute"
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(ProductAttribute, self.name)
        super().save(*a, **kw)


class ProductAttributeValue(BaseModel):
    attribute = models.ForeignKey(
        ProductAttribute, on_delete=models.CASCADE, related_name="values"
    )
    value = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    color_hex = models.CharField(max_length=7, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "products_attribute_value"
        ordering = ["attribute__position", "position", "value"]
        constraints = [
            models.UniqueConstraint(fields=["attribute", "value"], name="uniq_attribute_value"),
        ]

    def __str__(self) -> str:
        return f"{self.attribute.name}: {self.value}"

    def save(self, *a, **kw):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.value) or f"{self.attribute.slug}-{self.value[:10]}"
        super().save(*a, **kw)


class Product(BaseModel, PublishableModel, SoftDeleteModel):
    class Condition(models.TextChoices):
        NEW = "new", "New"
        REFURBISHED = "refurbished", "Refurbished"

    class ProductType(models.TextChoices):
        PHYSICAL = "physical", "Physical"
        DIGITAL = "digital", "Digital"
        CUSTOM = "custom", "Custom / made-to-order"

    sku = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=220, db_index=True)
    slug = models.SlugField(max_length=240, unique=True, db_index=True)
    category = models.ForeignKey(
        "categories.Category", on_delete=models.PROTECT, related_name="products"
    )
    brand = models.ForeignKey(
        Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )

    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    specifications = models.JSONField(
        default=dict, blank=True,
        help_text="Key/value specification sheet rendered on the product page.",
    )
    key_features = models.JSONField(
        default=list, blank=True, help_text="Ordered list of selling points.",
    )
    tags = models.JSONField(default=list, blank=True, help_text="Free-form tags for search.")
    search_keywords = models.CharField(
        max_length=500, blank=True, help_text="Extra keywords indexed for site search."
    )

    # pricing — base price; variations may override
    price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    compare_at_price = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text="Optional 'was' price for display. Never used for charging.",
    )
    cost_price = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Internal cost for margin reporting. Never exposed on public APIs.",
    )
    tax_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="NGN")

    product_type = models.CharField(
        max_length=20, choices=ProductType.choices, default=ProductType.PHYSICAL
    )
    condition = models.CharField(max_length=20, choices=Condition.choices, default=Condition.NEW)
    is_variation_based = models.BooleanField(default=False)
    attribute_values = models.ManyToManyField(
        ProductAttributeValue, blank=True, related_name="products"
    )

    # custom / made-to-order (fashion and tailoring)
    custom_order_enabled = models.BooleanField(default=False)
    custom_order_lead_time_days = models.PositiveSmallIntegerField(default=0)
    custom_order_instructions = models.TextField(blank=True)

    # merchandising
    is_featured = models.BooleanField(default=False, db_index=True)
    is_new_arrival = models.BooleanField(default=True, db_index=True)
    sold_count = models.PositiveIntegerField(default=0, editable=False)
    view_count = models.PositiveIntegerField(default=0, editable=False)
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, default=0, editable=False)
    rating_count = models.PositiveIntegerField(default=0, editable=False)

    # logistics
    weight_kg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    requires_shipping = models.BooleanField(default=True)
    is_heavy = models.BooleanField(default=False, help_text="May attract an extra delivery fee.")
    warranty = models.CharField(max_length=120, blank=True)

    # SEO (Section 25)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)
    meta_keywords = models.CharField(max_length=255, blank=True)
    og_image_url = models.URLField(blank=True)
    canonical_url = models.URLField(blank=True)
    noindex = models.BooleanField(default=False, help_text="Exclude this product from search engines.")
    structured_data = models.JSONField(default=dict, blank=True)

    objects = ProductManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "products_product"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "is_featured"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["-sold_count"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["price"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(price__gte=0), name="product_price_non_negative"),
            models.CheckConstraint(
                check=models.Q(compare_at_price__isnull=True) | models.Q(compare_at_price__gte=0),
                name="product_compare_price_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"

    # -- validation & persistence -----------------------------------------
    def clean(self):
        if self.compare_at_price is not None and self.compare_at_price < self.price:
            raise DjangoValidationError(
                {"compare_at_price": "The compare-at price must be greater than or equal to the price."}
            )
        if self.product_type != self.ProductType.CUSTOM and self.custom_order_enabled:
            raise DjangoValidationError(
                {"custom_order_enabled": "Custom orders are only valid for custom/made-to-order products."}
            )

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(Product, self.name)
        if self.sku:
            self.sku = self.sku.strip().upper()
        if self.status == PublishableModel.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        if not self.noindex and self.status == PublishableModel.Status.PUBLISHED:
            self.noindex = self.category.status != PublishableModel.Status.PUBLISHED
        super().save(*a, **kw)

    # -- pricing -----------------------------------------------------------
    def effective_price(self, variation: "ProductVariation | None" = None):
        """Authoritative selling price. Only this may be used for charging."""
        if variation is not None:
            if variation.product_id != self.pk:
                raise DjangoValidationError("Variation does not belong to this product.")
            return variation.effective_price
        return self.price

    @property
    def absolute_path(self) -> str:
        return f"/product/{self.slug}"

    def get_absolute_url(self) -> str:
        return self.absolute_path

    @property
    def primary_image(self) -> "ProductImage | None":
        images = list(self.images.all())
        for img in images:
            if img.is_primary:
                return img
        return images[0] if images else None

    @property
    def on_sale(self) -> bool:
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    @property
    def discount_percentage(self) -> int:
        if not self.on_sale:
            return 0
        return int(round((self.compare_at_price - self.price) / self.compare_at_price * 100))

    def is_purchasable(self) -> bool:
        return self.status == PublishableModel.Status.PUBLISHED and self.deleted_at is None

    def refresh_rating(self) -> None:
        """Recomputes the aggregate rating from approved reviews only."""
        from django.db.models import Avg, Count

        agg = self.reviews.filter(is_approved=True).aggregate(avg=Avg("rating"), count=Count("id"))
        self.rating_average = round(agg["avg"] or 0, 2)
        self.rating_count = agg["count"] or 0
        self.save(update_fields=["rating_average", "rating_count", "updated_at"])

    def build_structured_data(self) -> dict:
        """schema.org Product JSON-LD used by the public product page."""
        from django.conf import settings

        data = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": self.name,
            "sku": self.sku,
            "description": self.short_description or (self.description[:300] if self.description else ""),
            "url": f"{settings.SITE_URL}{self.absolute_path}",
            "brand": {"@type": "Brand", "name": self.brand.name if self.brand else settings.BUSINESS_NAME},
            "offers": {
                "@type": "Offer",
                "priceCurrency": self.currency,
                "price": str(self.price),
                "availability": "https://schema.org/InStock",
                "url": f"{settings.SITE_URL}{self.absolute_path}",
                "seller": {"@type": "Organization", "name": settings.BUSINESS_NAME},
            },
        }
        if self.rating_count:
            data["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": str(self.rating_average),
                "reviewCount": self.rating_count,
            }
        image = self.primary_image
        if image:
            data["image"] = [f"{settings.SITE_URL}{image.image.url}"]
        return data


class ProductImage(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    variation = models.ForeignKey(
        "products.ProductVariation", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/%Y/%m/")
    alt_text = models.CharField(max_length=200, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "products_image"
        ordering = ["position", "created_at"]
        indexes = [models.Index(fields=["product", "is_primary"])]

    def __str__(self) -> str:
        return f"Image<{self.product.sku}#{self.position}>"

    def save(self, *a, **kw):
        super().save(*a, **kw)
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)


class ProductVariation(BaseModel):
    """
    A concrete buyable SKU of a product (e.g. "Red / Large").

    Price and stock live here, never on the client.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variations")
    sku = models.CharField(max_length=64, unique=True, db_index=True)
    attribute_values = models.ManyToManyField(
        ProductAttributeValue, blank=True, related_name="variations"
    )
    price_override = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text="When set, replaces the product price for this variation.",
    )
    compare_at_price = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    image = models.ImageField(upload_to="products/variations/%Y/%m/", null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "products_variation"
        ordering = ["position", "sku"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price_override__isnull=True) | models.Q(price_override__gte=0),
                name="variation_price_non_negative",
            ),
        ]

    def __str__(self) -> str:
        label = " / ".join(v.value for v in self.attribute_values.all())
        return f"{self.product.name} — {label}" if label else self.sku

    @property
    def effective_price(self):
        return self.price_override if self.price_override is not None else self.product.price

    @property
    def label(self) -> str:
        return " / ".join(v.value for v in self.attribute_values.all())

    def save(self, *a, **kw):
        if self.sku:
            self.sku = self.sku.strip().upper()
        super().save(*a, **kw)
