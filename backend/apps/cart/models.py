"""
Server-authoritative carts for guests and signed-in customers.

The cart stores *intent* (which product/variation and how many) and never a
final price. Every displayed total is recalculated from the catalogue by
``PricingService`` so a tampered cart cannot change what is charged.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Cart(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONVERTED = "converted", "Converted to order"
        MERGED = "merged", "Merged into customer cart"
        ABANDONED = "abandoned", "Abandoned"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name="carts",
    )
    guest_email = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    currency = models.CharField(max_length=3, default="NGN")
    applied_codes = models.JSONField(
        default=list, blank=True, help_text="Promotion codes the customer has entered."
    )
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "cart_cart"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "last_activity_at"]),
        ]

    def __str__(self) -> str:
        owner = self.user_id or f"guest:{str(self.token)[:8]}"
        return f"Cart<{owner}>"

    @property
    def item_count(self) -> int:
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    @property
    def line_count(self) -> int:
        return self.items.count()

    def touch(self) -> None:
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at", "updated_at"])


class CartItem(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="cart_items")
    variation = models.ForeignKey(
        "products.ProductVariation", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    # Reference only: what the unit price was when added. Never used for charging.
    unit_price_at_add = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custom_order_details = models.JSONField(
        default=dict, blank=True,
        help_text="Measurements/notes captured for made-to-order fashion items.",
    )

    class Meta:
        db_table = "cart_item"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product", "variation"], name="uniq_cart_product_variation"
            ),
            models.CheckConstraint(check=models.Q(quantity__gte=1), name="cart_item_quantity_positive"),
        ]
        indexes = [models.Index(fields=["cart"])]

    def __str__(self) -> str:
        return f"{self.product_id} x{self.quantity}"

    @property
    def line_key(self) -> str:
        return f"{self.product_id}:{self.variation_id or 'base'}"
