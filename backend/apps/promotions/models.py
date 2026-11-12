"""
Discounts and promotions.

Eligibility, stacking and caps are always re-validated on the server at
checkout time — a coupon that was valid when the cart was built is re-checked
against the final, authoritative basket.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Promotion(BaseModel):
    class Type(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage off"
        FIXED_AMOUNT = "fixed_amount", "Fixed amount off"
        FREE_SHIPPING = "free_shipping", "Free shipping"

    class AppliesTo(models.TextChoices):
        ALL = "all", "Entire order"
        CATEGORIES = "categories", "Specific categories"
        PRODUCTS = "products", "Specific products"

    name = models.CharField(max_length=150)
    code = models.CharField(
        max_length=40, unique=True, null=True, blank=True, db_index=True,
        help_text="Leave blank for an automatic promotion that needs no code.",
    )
    description = models.TextField(blank=True)
    promotion_type = models.CharField(max_length=20, choices=Type.choices, default=Type.PERCENTAGE)
    value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        help_text="Percentage (0–100) or a fixed NGN amount, depending on the type.",
    )
    max_discount_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Hard cap on the money discounted, whatever the percentage.",
    )
    min_order_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Minimum eligible subtotal required to use this promotion.",
    )
    applies_to = models.CharField(max_length=20, choices=AppliesTo.choices, default=AppliesTo.ALL)
    categories = models.ManyToManyField("categories.Category", blank=True, related_name="promotions")
    products = models.ManyToManyField("products.Product", blank=True, related_name="promotions")

    starts_at = models.DateTimeField(default=timezone.now, db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)
    usage_limit_total = models.PositiveIntegerField(
        null=True, blank=True, help_text="Total redemptions allowed across all customers."
    )
    usage_limit_per_customer = models.PositiveIntegerField(
        null=True, blank=True, help_text="Redemptions allowed per customer account or email."
    )
    first_order_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    is_automatic = models.BooleanField(
        default=False, help_text="Applies without a code when the basket qualifies."
    )
    # Two coded promotions may be combined only when both allow stacking.
    is_stackable = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    public_label = models.CharField(max_length=120, blank=True, help_text="Badge text, e.g. '20% OFF'.")

    class Meta:
        db_table = "promotions_promotion"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code", "is_active"]),
            models.Index(fields=["starts_at", "ends_at"]),
            models.Index(fields=["is_automatic", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(value__gte=0), name="promotion_value_non_negative"),
            models.CheckConstraint(
                check=models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=models.F("starts_at")),
                name="promotion_window_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}{f' [{self.code}]' if self.code else ''}"

    def clean(self):
        if self.promotion_type == self.Type.PERCENTAGE and self.value > 100:
            raise DjangoValidationError({"value": "A percentage discount may not exceed 100."})
        if self.promotion_type in {self.Type.PERCENTAGE, self.Type.FIXED_AMOUNT} and self.value <= 0:
            raise DjangoValidationError({"value": "A monetary promotion must have a value above zero."})
        if self.ends_at and self.ends_at <= self.starts_at:
            raise DjangoValidationError({"ends_at": "The end date must be after the start date."})
        if self.applies_to == self.AppliesTo.CATEGORIES and self.pk and not self.categories.exists():
            raise DjangoValidationError(
                {"categories": "Select at least one category for a category promotion."}
            )
        if self.applies_to == self.AppliesTo.PRODUCTS and self.pk and not self.products.exists():
            raise DjangoValidationError(
                {"products": "Select at least one product for a product promotion."}
            )

    def save(self, *a, **kw):
        if self.code:
            self.code = self.code.strip().upper().replace(" ", "")
        super().save(*a, **kw)

    # -- state -------------------------------------------------------------
    @property
    def is_live(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True

    @property
    def is_exhausted(self) -> bool:
        if self.usage_limit_total is None:
            return False
        return self.usages.count() >= self.usage_limit_total

    @property
    def remaining_uses(self) -> int | None:
        if self.usage_limit_total is None:
            return None
        return max(self.usage_limit_total - self.usages.count(), 0)

    def usage_count_for(self, *, user=None, email: str = "") -> int:
        qs = self.usages.all()
        if user is not None:
            return qs.filter(user=user).count()
        if email:
            return qs.filter(customer_email__iexact=email).count()
        return qs.count()


class PromotionUsage(BaseModel):
    """One redemption. The permanent financial record of a discount."""

    promotion = models.ForeignKey(Promotion, on_delete=models.PROTECT, related_name="usages")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="promotion_usages",
    )
    customer_email = models.EmailField(blank=True)
    order = models.ForeignKey(
        "orders.Order", on_delete=models.CASCADE, related_name="promotion_usages"
    )
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")

    class Meta:
        db_table = "promotions_usage"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["promotion", "order"], name="uniq_promotion_per_order"
            ),
        ]
        indexes = [
            models.Index(fields=["promotion", "user"]),
            models.Index(fields=["customer_email"]),
        ]

    def __str__(self) -> str:
        return f"{self.promotion_id} → order {self.order_id} ({self.discount_amount})"
