"""Concurrency-safe inventory operations.

Every mutation locks the inventory row (SELECT ... FOR UPDATE) inside a
database transaction, so concurrent checkouts can NEVER oversell stock.
Negative inventory is additionally blocked by CHECK constraints.
"""
import logging

from django.db import transaction

from apps.core.exceptions import StockUnavailableError, ServiceError

from .models import Inventory, InventoryMovement

logger = logging.getLogger("starmond.inventory")


def _record(inventory, movement_type, quantity_change, order=None, performed_by=None, reason="",
            before=None, after=None):
    before = before or (inventory.on_hand, inventory.reserved)
    after = after or (inventory.on_hand, inventory.reserved)
    return InventoryMovement.objects.create(
        inventory=inventory, product=inventory.product, variation=inventory.variation,
        movement_type=movement_type, quantity_change=quantity_change,
        on_hand_before=before[0], on_hand_after=after[0],
        reserved_before=before[1], reserved_after=after[1],
        order=order, performed_by=performed_by, reason=reason[:255],
    )


class InventoryService:
    MT = InventoryMovement.MovementType

    @staticmethod
    def _locked(inventory_id):
        return Inventory.objects.select_for_update().select_related("product").get(pk=inventory_id)

    @classmethod
    @transaction.atomic
    def ensure_inventory(cls, product, variation=None, opening=None):
        inventory, created = Inventory.objects.get_or_create(product=product, variation=variation)
        if opening is not None and (created or not inventory.movements.exists()):
            cls.set_opening_stock(inventory, int(opening))
        return inventory

    @classmethod
    @transaction.atomic
    def set_opening_stock(cls, inventory, quantity):
        if quantity < 0:
            raise ServiceError("Opening stock cannot be negative.", code="invalid_quantity")
        inv = cls._locked(inventory.pk)
        before = (inv.on_hand, inv.reserved)
        inv.on_hand = quantity
        inv.save(update_fields=["on_hand", "updated_at"])
        _record(inv, cls.MT.OPENING, quantity - before[0], before=before, after=(inv.on_hand, inv.reserved))
        cls.sync_product_status(inv.product)
        return inv

    @classmethod
    @transaction.atomic
    def receive_stock(cls, inventory, quantity, performed_by=None, reason=""):
        if quantity <= 0:
            raise ServiceError("Received quantity must be positive.", code="invalid_quantity")
        inv = cls._locked(inventory.pk)
        before = (inv.on_hand, inv.reserved)
        inv.on_hand += quantity
        inv.save(update_fields=["on_hand", "updated_at"])
        _record(inv, cls.MT.RECEIVED, quantity, performed_by=performed_by, reason=reason or "Stock received",
                before=before, after=(inv.on_hand, inv.reserved))
        cls.sync_product_status(inv.product)
        return inv

    @classmethod
    @transaction.atomic
    def reserve(cls, inventory, quantity, order=None, reason="Order reservation"):
        """Reserve stock for a pending order. Raises StockUnavailableError."""
        if quantity <= 0:
            raise ServiceError("Quantity must be positive.", code="invalid_quantity")
        inv = cls._locked(inventory.pk)
        if inv.available < quantity:
            raise StockUnavailableError(
                f"Only {inv.available} unit(s) available for {inv.product.name}"
                + (f" ({inv.variation.display_name})" if inv.variation else "") + "."
            )
        before = (inv.on_hand, inv.reserved)
        inv.reserved += quantity
        inv.save(update_fields=["reserved", "updated_at"])
        _record(inv, cls.MT.RESERVED, quantity, order=order, reason=reason,
                before=before, after=(inv.on_hand, inv.reserved))
        return inv

    @classmethod
    @transaction.atomic
    def confirm_sale(cls, inventory, quantity, order=None):
        """Finalize stock after VERIFIED payment: reserved -> sold."""
        inv = cls._locked(inventory.pk)
        if inv.reserved < quantity:
            raise ServiceError("Reservation missing for confirmed sale.", code="reservation_missing", status_code=409)
        before = (inv.on_hand, inv.reserved)
        inv.reserved -= quantity
        inv.on_hand -= quantity
        inv.save(update_fields=["on_hand", "reserved", "updated_at"])
        _record(inv, cls.MT.SOLD, -quantity, order=order, reason="Payment confirmed",
                before=before, after=(inv.on_hand, inv.reserved))
        cls.sync_product_status(inv.product)
        return inv

    @classmethod
    @transaction.atomic
    def release(cls, inventory, quantity, order=None, reason="Reservation released"):
        """Release reservation (payment expiry, cancellation before payment)."""
        inv = cls._locked(inventory.pk)
        release_qty = min(quantity, inv.reserved)
        if release_qty <= 0:
            return inv
        before = (inv.on_hand, inv.reserved)
        inv.reserved -= release_qty
        inv.save(update_fields=["reserved", "updated_at"])
        _record(inv, cls.MT.RELEASED, -release_qty, order=order, reason=reason,
                before=before, after=(inv.on_hand, inv.reserved))
        cls.sync_product_status(inv.product)
        return inv

    @classmethod
    @transaction.atomic
    def restore(cls, inventory, quantity, order=None, performed_by=None, reason="Returned to stock"):
        """Return stock after an authorized return/restock (post-payment)."""
        if quantity <= 0:
            raise ServiceError("Quantity must be positive.", code="invalid_quantity")
        inv = cls._locked(inventory.pk)
        before = (inv.on_hand, inv.reserved)
        inv.on_hand += quantity
        inv.save(update_fields=["on_hand", "updated_at"])
        _record(inv, cls.MT.RETURNED, quantity, order=order, performed_by=performed_by, reason=reason,
                before=before, after=(inv.on_hand, inv.reserved))
        cls.sync_product_status(inv.product)
        return inv

    @classmethod
    @transaction.atomic
    def adjust(cls, inventory, delta, performed_by, reason):
        """Manual adjustment (delta may be negative). Reason is MANDATORY."""
        if not reason or not reason.strip():
            raise ServiceError("A reason is required for stock adjustments.", code="reason_required")
        inv = cls._locked(inventory.pk)
        before = (inv.on_hand, inv.reserved)
        new_on_hand = inv.on_hand + delta
        if new_on_hand < inv.reserved:
            raise ServiceError(
                f"Adjustment would put on-hand stock below active reservations ({inv.reserved}).",
                code="below_reservations", status_code=409)
        if new_on_hand < 0:
            raise ServiceError("Adjustment would result in negative stock.", code="negative_stock", status_code=409)
        inv.on_hand = new_on_hand
        inv.save(update_fields=["on_hand", "updated_at"])
        _record(inv, cls.MT.ADJUSTMENT, delta, performed_by=performed_by, reason=reason,
                before=before, after=(inv.on_hand, inv.reserved))
        cls.sync_product_status(inv.product)
        return inv

    # ------------------------------------------------------------------ reads
    @staticmethod
    def resolve_inventory(product, variation=None):
        """Return the authoritative Inventory row for a product/variation."""
        from .models import Inventory
        if variation is not None:
            return Inventory.objects.filter(product=product, variation=variation).first()
        return Inventory.objects.filter(product=product, variation__isnull=True).first()

    @staticmethod
    def product_summary(product):
        records = list(product.inventory_records.all())
        on_hand = sum(r.on_hand for r in records)
        reserved = sum(r.reserved for r in records)
        return {"on_hand": on_hand, "reserved": reserved, "available": on_hand - reserved}

    @staticmethod
    def sync_product_status(product):
        """Keep the product's OUT_OF_STOCK status consistent with real stock."""
        from apps.products.models import Product
        summary = InventoryService.product_summary(product)
        fresh = Product.objects.filter(pk=product.pk).values("status").first()
        if not fresh:
            return
        current = fresh["status"]
        if summary["available"] <= 0 and current == Product.Status.ACTIVE:
            Product.objects.filter(pk=product.pk).update(status=Product.Status.OUT_OF_STOCK)
        elif summary["available"] > 0 and current == Product.Status.OUT_OF_STOCK:
            Product.objects.filter(pk=product.pk).update(status=Product.Status.ACTIVE)
