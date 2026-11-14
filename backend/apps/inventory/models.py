from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Inventory(TimeStampedModel):
    """Authoritative stock record at product-variation level.

    AVAILABLE STOCK = ON_HAND - RESERVED  (computed, never stored twice).
    CHECK constraints enforce non-negative stock at the database level.
    """
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="inventory_records")
    variation = models.OneToOneField("products.ProductVariation", on_delete=models.CASCADE,
                                     null=True, blank=True, related_name="inventory_record")
    on_hand = models.IntegerField(default=0)
    reserved = models.IntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(null=True, blank=True,
        help_text="Overrides the product default when set.")

    class Meta:
        db_table = "inventory_stock"
        constraints = [
            models.UniqueConstraint(fields=["product", "variation"], name="unique_inventory_per_variation"),
            models.UniqueConstraint(fields=["product"], name="unique_base_inventory_per_product",
                                      condition=models.Q(variation__isnull=True)),
            models.CheckConstraint(check=models.Q(on_hand__gte=0), name="inventory_on_hand_non_negative"),
            models.CheckConstraint(check=models.Q(reserved__gte=0), name="inventory_reserved_non_negative"),
            models.CheckConstraint(check=models.Q(on_hand__gte=models.F("reserved")), name="inventory_reserved_within_on_hand"),
        ]

    def __str__(self):
        return f"inventory:{self.product.sku}:{self.variation.sku if self.variation else '-'}"

    @property
    def available(self):
        return self.on_hand - self.reserved

    @property
    def effective_threshold(self):
        return self.low_stock_threshold if self.low_stock_threshold is not None else self.product.low_stock_threshold

    @property
    def is_low_stock(self):
        return self.available > 0 and self.available <= self.effective_threshold

    @property
    def is_out_of_stock(self):
        return self.available <= 0


class InventoryMovement(models.Model):
    class MovementType(models.TextChoices):
        OPENING = "opening", "Opening stock"
        RECEIVED = "received", "Stock received"
        RESERVED = "reserved", "Reserved for order"
        RELEASED = "released", "Reservation released"
        SOLD = "sold", "Sold (payment confirmed)"
        RETURNED = "returned", "Returned to stock"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name="movements")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="inventory_movements")
    variation = models.ForeignKey("products.ProductVariation", on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_movements")
    movement_type = models.CharField(max_length=12, choices=MovementType.choices, db_index=True)
    quantity_change = models.IntegerField(help_text="Signed change to on_hand or reserved.")
    on_hand_before = models.IntegerField()
    on_hand_after = models.IntegerField()
    reserved_before = models.IntegerField()
    reserved_after = models.IntegerField()
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_movements")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_movements")
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "inventory_movement"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["inventory", "-created_at"]), models.Index(fields=["movement_type", "-created_at"])]

    def __str__(self):
        return f"{self.movement_type}:{self.product.sku}:{self.quantity_change:+d}"
