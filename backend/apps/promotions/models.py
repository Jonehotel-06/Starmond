from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Promotion(TimeStampedModel):
    class Kind(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage discount"
        FIXED = "fixed", "Fixed amount discount"

    class Scope(models.TextChoices):
        ALL = "all", "Entire order"
        PRODUCTS = "products", "Specific products"
        CATEGORIES = "categories", "Specific categories"

    code = models.CharField(max_length=40, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    value = models.DecimalField(max_digits=12, decimal_places=2, help_text="Percent (0-100) or fixed NGN amount.")
    scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.ALL)
    product_ids = models.JSONField(default=list, blank=True)
    category_ids = models.JSONField(default=list, blank=True)
    min_purchase_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Total redemptions allowed.")
    usage_limit_per_customer = models.PositiveIntegerField(default=1)
    applies_to_sale_items = models.BooleanField(default=True)
    first_time_customers_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    banner_image = models.ImageField(upload_to="promotions/", blank=True, null=True)

    class Meta:
        db_table = "promotions_promotion"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(value__gt=0), name="promotion_value_positive"),
            models.CheckConstraint(
                check=~models.Q(kind="percentage") | models.Q(value__lte=100),
                name="promotion_percentage_max_100"),
        ]

    def __str__(self):
        return self.code

    @property
    def is_within_window(self):
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    @property
    def total_usages(self):
        return self.usages.count()

    @property
    def banner_image_url(self):
        return self.banner_image.url if self.banner_image else None


class PromotionUsage(TimeStampedModel):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name="usages")
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="promotion_usage")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="promotion_usages")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "promotions_usage"
        ordering = ["-created_at"]
