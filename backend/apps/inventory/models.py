"""
Inventory: on-hand stock, reservations, movements.

Authoritative formula (Section 14 / Section 45 rule 13):

    AVAILABLE STOCK = ON-HAND STOCK - ACTIVE RESERVED QUANTITY

Stock is tracked per product *and* per variation. Negative on-hand or negative
reserved quantities are impossible by database constraint, and every mutation
happens under ``select_for_update()`` inside a transaction.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, TimeStampedModel


class Inventory(BaseModel):
    """Stock record for a product or a specific product variation."""

    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="inventories"
    )
    variation = models.ForeignKey(
        "products.ProductVariation", null=True, blank=True, on_delete=models.CASCADE,
        related_name="inventories",
    )
    quantity_on_hand = models.IntegerField(default=0)
    quantity_reserved = models.IntegerField(default=0)
    quantity_sold = models.IntegerField(default=0)
    quantity_returned = models.IntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(
        default=settings.LOW_STOCK_DEFAULT_THRESHOLD
    )
    track_inventory = models.BooleanField(
        default=True, help_text="When false the item is unlimited (e.g. services)."
    )
    allow_backorder = models.BooleanField(default=False)
    last_restocked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inventory_inventory"
        verbose_name_plural = "Inventory"
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity_on_hand__gte=0), name="inventory_on_hand_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(quantity_reserved__gte=0), name="inventory_reserved_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(quantity_reserved__lte=models.F("quantity_on_hand")),
                name="inventory_reserved_lte_on_hand",
            ),
            models.UniqueConstraint(
                fields=["product", "variation"], name="uniq_inventory_product_variation",
                condition=models.Q(variation__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["product"], name="uniq_inventory_product_no_variation",
                condition=models.Q(variation__isnull=True),
            ),
        ]
        indexes = [
            models.Index(fields=["product", "variation"]),
        ]

    def __str__(self) -> str:
        label = self.variation.sku if self.variation else self.product.sku
        return f"{label}: {self.quantity_on_hand} on hand / {self.quantity_reserved} reserved"

    @property
    def available_quantity(self) -> int:
        """The only number a customer may be shown or sold against."""
        if not self.track_inventory:
            return 10**6
        return max(self.quantity_on_hand - self.quantity_reserved, 0)

    @property
    def is_low_stock(self) -> bool:
        return self.track_inventory and self.available_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self) -> bool:
        return self.track_inventory and self.available_quantity <= 0 and not self.allow_backorder

    def can_fulfil(self, quantity: int) -> bool:
        if not self.track_inventory:
            return True
        if quantity <= 0:
            return False
        return self.available_quantity >= quantity or self.allow_backorder

    @property
    def stock_status(self) -> str:
        if not self.track_inventory:
            return "in_stock"
        available = self.available_quantity
        if available <= 0:
            return "backorder" if self.allow_backorder else "out_of_stock"
        if available <= self.low_stock_threshold:
            return "low_stock"
        return "in_stock"


class InventoryReservation(BaseModel):
    """
    A hold against on-hand stock created when an order is placed and released
    or consumed when that order expires, is cancelled, or is paid for.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"
        COMMITTED = "committed", "Committed (sold)"
        EXPIRED = "expired", "Expired"

    inventory = models.ForeignKey(
        Inventory, on_delete=models.CASCADE, related_name="reservations"
    )
    order_item = models.ForeignKey(
        "orders.OrderItem", null=True, blank=True, on_delete=models.CASCADE,
        related_name="reservations",
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    expires_at = models.DateTimeField(db_index=True)
    released_at = models.DateTimeField(null=True, blank=True)
    reference = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        db_table = "inventory_reservation"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["inventory", "status"]),
        ]

    def __str__(self) -> str:
        return f"Reservation<{self.inventory_id}:{self.quantity}:{self.status}>"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE and self.expires_at > timezone.now()


class InventoryMovement(BaseModel):
    """Append-only ledger of every stock change, with before/after snapshots."""

    class Type(models.TextChoices):
        OPENING = "opening", "Opening stock"
        RECEIVED = "received", "Stock received"
        RESERVED = "reserved", "Stock reserved"
        RELEASED = "released", "Reservation released"
        SOLD = "sold", "Stock sold"
        RETURNED = "returned", "Stock returned"
        ADJUSTMENT = "adjustment", "Manual adjustment"
        DAMAGE = "damage", "Damage / write-off"
        CORRECTION = "correction", "Correction"

    class Direction(models.TextChoices):
        IN = "in", "In"
        OUT = "out", "Out"
        HOLD = "hold", "Hold"
        NONE = "none", "No change to on-hand"

    inventory = models.ForeignKey(
        Inventory, on_delete=models.CASCADE, related_name="movements"
    )
    movement_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.NONE)
    quantity = models.IntegerField(help_text="Signed delta applied to on-hand stock.")
    reserved_delta = models.IntegerField(default=0, help_text="Signed delta applied to reservations.")
    on_hand_before = models.IntegerField()
    on_hand_after = models.IntegerField()
    reserved_before = models.IntegerField(default=0)
    reserved_after = models.IntegerField(default=0)
    reference_type = models.CharField(max_length=60, blank=True, db_index=True)
    reference_id = models.CharField(max_length=64, blank=True, db_index=True)
    reason = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="inventory_movements",
    )

    class Meta:
        db_table = "inventory_movement"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["inventory", "-created_at"]),
            models.Index(fields=["movement_type", "-created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.quantity:+d} → {self.on_hand_after}"

    def save(self, *a, **kw):
        if not self._state.adding:
            raise PermissionError("Inventory movements are immutable ledger entries.")
        return super().save(*a, **kw)

    def delete(self, *a, **kw):
        raise PermissionError("Inventory movements cannot be deleted.")
