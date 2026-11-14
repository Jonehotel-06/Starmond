from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.references import cart_token


class Cart(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MERGED = "merged", "Merged into another cart"
        CONVERTED = "converted", "Converted to order"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="carts")
    token = models.CharField(max_length=64, unique=True, default=cart_token, db_index=True,
                             help_text="Public identifier for guest carts (X-Cart-Token header).")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    merged_into = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="merged_carts")

    class Meta:
        db_table = "cart_cart"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user"], name="one_active_cart_per_user",
                                      condition=models.Q(status="active", user__isnull=False)),
        ]

    def __str__(self):
        return f"cart:{self.token[:12]}"

    @property
    def item_count(self):
        return sum(i.quantity for i in self.items.all())


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="cart_items")
    variation = models.ForeignKey("products.ProductVariation", on_delete=models.CASCADE, null=True, blank=True, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "cart_item"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product", "variation"], name="unique_cart_line"),
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="cart_quantity_positive"),
        ]

    @property
    def unit_price(self):
        return self.variation.effective_price if self.variation else self.product.effective_price

    @property
    def line_total(self):
        return self.unit_price * self.quantity
