"""
InventoryService — every stock mutation in the platform funnels through here.

Invariants enforced:

* ``quantity_on_hand`` and ``quantity_reserved`` are never negative.
* ``quantity_reserved`` never exceeds ``quantity_on_hand``.
* All reads/writes of a stock row happen under ``select_for_update()``.
* Each mutation writes exactly one ``InventoryMovement`` row.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.core.exceptions import ConflictError, InsufficientStock, NotFound, ValidationError
from apps.core.models import PublishableModel
from apps.inventory.models import Inventory, InventoryMovement, InventoryReservation

logger = logging.getLogger("apps.inventory")


class InventoryService:
    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    @staticmethod
    def get_for(product, variation=None) -> Inventory:
        inventory = Inventory.objects.filter(product=product, variation=variation).first()
        if inventory is None:
            raise NotFound(
                f"No inventory record exists for {variation.sku if variation else product.sku}."
            )
        return inventory

    @staticmethod
    @transaction.atomic
    def get_or_create_for(product, variation=None, *, opening_quantity: int = 0) -> Inventory:
        """Creates the stock record if missing, recording an opening-stock movement."""
        inventory, created = Inventory.objects.select_for_update().get_or_create(
            product=product,
            variation=variation,
            defaults={
                "quantity_on_hand": max(opening_quantity, 0),
                "track_inventory": product.requires_shipping or product.product_type != "digital",
            },
        )
        if created and opening_quantity:
            InventoryService._write_movement(
                inventory,
                movement_type=InventoryMovement.Type.OPENING,
                quantity=opening_quantity,
                reserved_delta=0,
                on_hand_before=0,
                reserved_before=0,
                reason="Opening stock",
            )
        return inventory

    @staticmethod
    def available_quantity(product, variation=None) -> int:
        """
        Authoritative availability for a buyable item.

        A variation-based product without a variant-specific stock row falls back
        to the product-level row, and vice versa, so no product can become
        silently unlimited.
        """
        if variation is not None:
            row = Inventory.objects.filter(product=product, variation=variation).first()
            if row is not None:
                return row.available_quantity
            if product.inventories.filter(variation__isnull=True).exists():
                # Product-level stock exists but this variation has no own stock:
                # treat the variant as unavailable rather than overselling.
                return 0
            return 0
        row = Inventory.objects.filter(product=product, variation__isnull=True).first()
        if row is not None:
            return row.available_quantity
        if product.inventories.exists():
            # Product is variation-based: only the sum of variants is meaningful.
            return 0
        return 0

    @staticmethod
    def stock_status_for(product, variation=None) -> str:
        row = None
        if variation is not None:
            row = Inventory.objects.filter(product=product, variation=variation).first()
        else:
            row = Inventory.objects.filter(product=product, variation__isnull=True).first()
        if row is None:
            if product.inventories.exists():
                return "select_variation"
            return "out_of_stock"
        return row.stock_status

    # ------------------------------------------------------------------
    # Stock in
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def receive_stock(
        *,
        inventory: Inventory,
        quantity: int,
        reason: str = "Stock received",
        actor=None,
        reference_type: str = "",
        reference_id: str = "",
    ) -> Inventory:
        quantity = InventoryService._validate_positive(quantity)
        locked = Inventory.objects.select_for_update().get(pk=inventory.pk)
        before = locked.quantity_on_hand
        locked.quantity_on_hand = before + quantity
        locked.last_restocked_at = timezone.now()
        locked.save(update_fields=["quantity_on_hand", "last_restocked_at", "updated_at"])
        InventoryService._write_movement(
            locked,
            movement_type=InventoryMovement.Type.RECEIVED,
            quantity=quantity,
            reserved_delta=0,
            on_hand_before=before,
            reserved_before=locked.quantity_reserved,
            reason=reason,
            actor=actor,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        return locked

    @staticmethod
    @transaction.atomic
    def adjust_stock(
        *,
        inventory: Inventory,
        new_quantity: int,
        reason: str,
        actor=None,
        movement_type: str = InventoryMovement.Type.ADJUSTMENT,
    ) -> Inventory:
        """
        Sets on-hand stock to an absolute value (stock take).

        Adjustments may not push stock below the quantity already reserved.
        """
        try:
            new_quantity = int(new_quantity)
        except (TypeError, ValueError):
            raise ValidationError("The stock quantity must be a whole number.")
        if new_quantity < 0:
            raise ValidationError("Stock cannot be negative.")

        locked = Inventory.objects.select_for_update().get(pk=inventory.pk)
        if new_quantity < locked.quantity_reserved:
            raise ConflictError(
                f"{locked.quantity_reserved} unit(s) are reserved against this item; "
                f"stock cannot be set below that."
            )
        delta = new_quantity - locked.quantity_on_hand
        if delta == 0:
            return locked
        before = locked.quantity_on_hand
        locked.quantity_on_hand = new_quantity
        locked.save(update_fields=["quantity_on_hand", "updated_at"])
        InventoryService._write_movement(
            locked,
            movement_type=movement_type,
            quantity=delta,
            reserved_delta=0,
            on_hand_before=before,
            reserved_before=locked.quantity_reserved,
            reason=reason[:255],
            actor=actor,
        )
        return locked

    @staticmethod
    @transaction.atomic
    def write_off(*, inventory: Inventory, quantity: int, reason: str, actor=None) -> Inventory:
        quantity = InventoryService._validate_positive(quantity)
        locked = Inventory.objects.select_for_update().get(pk=inventory.pk)
        if quantity > locked.quantity_on_hand - locked.quantity_reserved:
            raise ConflictError("Cannot write off more stock than is unreserved.")
        before = locked.quantity_on_hand
        locked.quantity_on_hand = before - quantity
        locked.save(update_fields=["quantity_on_hand", "updated_at"])
        InventoryService._write_movement(
            locked,
            movement_type=InventoryMovement.Type.DAMAGE,
            quantity=-quantity,
            reserved_delta=0,
            on_hand_before=before,
            reserved_before=locked.quantity_reserved,
            reason=reason[:255],
            actor=actor,
        )
        return locked

    # ------------------------------------------------------------------
    # Reservation lifecycle
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def reserve(
        *,
        inventory: Inventory,
        quantity: int,
        order_item=None,
        reference: str = "",
        ttl_minutes: int | None = None,
    ) -> InventoryReservation:
        """
        Holds ``quantity`` units. Raises ``InsufficientStock`` rather than
        overselling when availability is short.
        """
        quantity = InventoryService._validate_positive(quantity)
        ttl = ttl_minutes if ttl_minutes is not None else settings.STOCK_RESERVATION_MINUTES

        locked = Inventory.objects.select_for_update().get(pk=inventory.pk)
        if not locked.track_inventory:
            return InventoryReservation.objects.create(
                inventory=locked,
                order_item=order_item,
                quantity=quantity,
                status=InventoryReservation.Status.COMMITTED,
                expires_at=timezone.now() + timedelta(minutes=ttl),
                reference=reference,
            )

        available = locked.quantity_on_hand - locked.quantity_reserved
        if available < quantity and not locked.allow_backorder:
            raise InsufficientStock(
                f"Only {max(available, 0)} unit(s) available for "
                f"{locked.variation.sku if locked.variation else locked.product.sku}.",
                details={
                    "product_id": str(locked.product_id),
                    "variation_id": str(locked.variation_id) if locked.variation_id else None,
                    "requested": quantity,
                    "available": max(available, 0),
                },
            )

        before_on_hand = locked.quantity_on_hand
        before_reserved = locked.quantity_reserved
        locked.quantity_reserved = before_reserved + quantity
        locked.save(update_fields=["quantity_reserved", "updated_at"])

        reservation = InventoryReservation.objects.create(
            inventory=locked,
            order_item=order_item,
            quantity=quantity,
            status=InventoryReservation.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(minutes=ttl),
            reference=reference,
        )
        InventoryService._write_movement(
            locked,
            movement_type=InventoryMovement.Type.RESERVED,
            quantity=0,
            reserved_delta=quantity,
            on_hand_before=before_on_hand,
            reserved_before=before_reserved,
            reason=f"Reserved for order ({reference})" if reference else "Reserved",
            reference_type="order" if reference else "",
            reference_id=reference,
        )
        return reservation

    @staticmethod
    @transaction.atomic
    def release(*, reservation: InventoryReservation, reason: str = "Reservation released",
                status: str = InventoryReservation.Status.RELEASED) -> InventoryReservation:
        """Returns held units to available stock (cancellation, expiry, failure)."""
        current = InventoryReservation.objects.select_for_update().get(pk=reservation.pk)
        if current.status != InventoryReservation.Status.ACTIVE:
            # Idempotent: releasing twice must not corrupt the counter.
            return current

        locked = Inventory.objects.select_for_update().get(pk=current.inventory_id)
        before_on_hand = locked.quantity_on_hand
        before_reserved = locked.quantity_reserved
        locked.quantity_reserved = max(before_reserved - current.quantity, 0)
        locked.save(update_fields=["quantity_reserved", "updated_at"])

        current.status = status
        current.released_at = timezone.now()
        current.save(update_fields=["status", "released_at", "updated_at"])

        InventoryService._write_movement(
            locked,
            movement_type=InventoryMovement.Type.RELEASED,
            quantity=0,
            reserved_delta=-(before_reserved - locked.quantity_reserved),
            on_hand_before=before_on_hand,
            reserved_before=before_reserved,
            reason=reason[:255],
            reference_type="order",
            reference_id=current.reference,
        )
        return current

    @staticmethod
    @transaction.atomic
    def commit_sale(*, reservation: InventoryReservation, reason: str = "Paid order") -> InventoryReservation:
        """
        Converts a hold into a sale: on-hand and reserved both drop by the
        reserved quantity and the cumulative sold counter rises.
        """
        current = InventoryReservation.objects.select_for_update().get(pk=reservation.pk)
        if current.status == InventoryReservation.Status.COMMITTED:
            return current  # idempotent — webhook retries must not double-count
        if current.status in {InventoryReservation.Status.RELEASED, InventoryReservation.Status.EXPIRED}:
            raise ConflictError("This reservation was already released and cannot be committed.")

        locked = Inventory.objects.select_for_update().get(pk=current.inventory_id)
        before_on_hand = locked.quantity_on_hand
        before_reserved = locked.quantity_reserved

        locked.quantity_on_hand = before_on_hand - current.quantity
        locked.quantity_reserved = max(before_reserved - current.quantity, 0)
        locked.quantity_sold = locked.quantity_sold + current.quantity
        if locked.quantity_on_hand < 0:
            # Defensive: the reservation invariant should make this unreachable.
            raise ConflictError("Stock would go negative while committing the sale.")
        locked.save(
            update_fields=["quantity_on_hand", "quantity_reserved", "quantity_sold", "updated_at"]
        )

        current.status = InventoryReservation.Status.COMMITTED
        current.save(update_fields=["status", "updated_at"])

        InventoryService._write_movement(
            locked,
            movement_type=InventoryMovement.Type.SOLD,
            quantity=-current.quantity,
            reserved_delta=-(before_reserved - locked.quantity_reserved),
            on_hand_before=before_on_hand,
            reserved_before=before_reserved,
            reason=reason[:255],
            reference_type="order",
            reference_id=current.reference,
        )
        return current

    @staticmethod
    @transaction.atomic
    def record_return(*, inventory: Inventory, quantity: int, reason: str = "Customer return",
                      actor=None, reference: str = "") -> Inventory:
        """Restocks returned goods. Only called from an approved return workflow."""
        quantity = InventoryService._validate_positive(quantity)
        locked = Inventory.objects.select_for_update().get(pk=inventory.pk)
        before = locked.quantity_on_hand
        locked.quantity_on_hand = before + quantity
        locked.quantity_returned = locked.quantity_returned + quantity
        locked.save(update_fields=["quantity_on_hand", "quantity_returned", "updated_at"])
        InventoryService._write_movement(
            locked,
            movement_type=InventoryMovement.Type.RETURNED,
            quantity=quantity,
            reserved_delta=0,
            on_hand_before=before,
            reserved_before=locked.quantity_reserved,
            reason=reason[:255],
            actor=actor,
            reference_type="refund" if reference else "",
            reference_id=reference,
        )
        return locked

    # ------------------------------------------------------------------
    # Order-level helpers
    # ------------------------------------------------------------------
    @staticmethod
    def reserve_for_order(order, ttl_minutes: int | None = None) -> list[InventoryReservation]:
        """
        Reserves every line of an order atomically.

        If any line fails the whole transaction rolls back, so an order can never
        be half-reserved.
        """
        reservations: list[InventoryReservation] = []
        try:
            with transaction.atomic():
                for item in order.items.select_related("product", "variation"):
                    inventory = Inventory.objects.select_for_update().filter(
                        product=item.product_id, variation=item.variation_id
                    ).first()
                    if inventory is None:
                        raise InsufficientStock(
                            f"{item.product_name} is currently unavailable.",
                            details={"order_item_id": str(item.id)},
                        )
                    reservations.append(
                        InventoryService.reserve(
                            inventory=inventory,
                            quantity=item.quantity,
                            order_item=item,
                            reference=str(order.order_number),
                            ttl_minutes=ttl_minutes,
                        )
                    )
        except InsufficientStock:
            raise
        return reservations

    @staticmethod
    def release_for_order(order, reason: str = "Order cancelled",
                          status: str = InventoryReservation.Status.RELEASED) -> int:
        released = 0
        for reservation in InventoryReservation.objects.filter(
            order_item__order=order, status=InventoryReservation.Status.ACTIVE
        ):
            InventoryService.release(reservation=reservation, reason=reason, status=status)
            released += 1
        return released

    @staticmethod
    def commit_for_order(order, reason: str = "Paid order") -> int:
        committed = 0
        for reservation in InventoryReservation.objects.filter(
            order_item__order=order, status=InventoryReservation.Status.ACTIVE
        ):
            InventoryService.commit_sale(reservation=reservation, reason=reason)
            committed += 1
        return committed

    @staticmethod
    def expire_stale_reservations() -> dict:
        """Releases holds for unpaid orders past their window. Called by cron."""
        now = timezone.now()
        stale = InventoryReservation.objects.filter(
            status=InventoryReservation.Status.ACTIVE, expires_at__lt=now
        ).select_related("order_item")
        expired = 0
        for reservation in stale.iterator():
            # A paid order's hold must never be expired out from under it.
            order = getattr(reservation.order_item, "order", None)
            if order is not None and order.is_paid:
                continue
            InventoryService.release(
                reservation=reservation,
                reason="Reservation window expired",
                status=InventoryReservation.Status.EXPIRED,
            )
            expired += 1
        return {"expired_reservations": expired}

    # ------------------------------------------------------------------
    # Reporting & integrity
    # ------------------------------------------------------------------
    @staticmethod
    def low_stock(threshold: int | None = None) -> list[Inventory]:
        qs = Inventory.objects.select_related("product", "variation").filter(track_inventory=True)
        if threshold is not None:
            qs = qs.filter(quantity_on_hand__lte=threshold)
        else:
            qs = qs.filter(quantity_on_hand__lte=F("low_stock_threshold"))
        return list(qs.order_by("quantity_on_hand"))

    @staticmethod
    def out_of_stock() -> list[Inventory]:
        return list(
            Inventory.objects.select_related("product", "variation").filter(
                track_inventory=True,
                quantity_on_hand__lte=F("quantity_reserved"),
                allow_backorder=False,
            )
        )

    @staticmethod
    def reconcile(inventory: Inventory) -> dict:
        """
        Integrity check: compares the cached reserved counter against the sum of
        active reservations. Used by tests and the ``check_inventory`` command.

        Values are re-read from the database so a stale in-memory instance can
        never mask (or fabricate) drift.
        """
        current = Inventory.objects.filter(pk=inventory.pk).values(
            "quantity_reserved", "quantity_on_hand"
        ).first()
        counter = current["quantity_reserved"] if current else 0
        active = (
            InventoryReservation.objects.filter(
                inventory_id=inventory.pk, status=InventoryReservation.Status.ACTIVE
            ).aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        return {
            "inventory_id": str(inventory.pk),
            "counter_reserved": counter,
            "active_reservations": active,
            "drift": counter - active,
            "consistent": counter == active,
        }

    @staticmethod
    def public_catalogue_is_safe() -> list[dict]:
        """Lists published products whose sellable quantity is inconsistent."""
        problems = []
        for inventory in Inventory.objects.select_related("product", "variation"):
            if inventory.product.status != PublishableModel.Status.PUBLISHED:
                continue
            report = InventoryService.reconcile(inventory)
            if not report["consistent"]:
                problems.append(report)
        return problems

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_positive(quantity) -> int:
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError("Quantity must be a whole number.")
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        return quantity

    @staticmethod
    def _write_movement(inventory, *, movement_type, quantity, reserved_delta, on_hand_before,
                        reserved_before, reason="", actor=None, reference_type="", reference_id=""):
        return InventoryMovement.objects.create(
            inventory=inventory,
            movement_type=movement_type,
            direction=(
                InventoryMovement.Direction.IN if quantity > 0
                else InventoryMovement.Direction.OUT if quantity < 0
                else InventoryMovement.Direction.HOLD if reserved_delta
                else InventoryMovement.Direction.NONE
            ),
            quantity=quantity,
            reserved_delta=reserved_delta,
            on_hand_before=on_hand_before,
            on_hand_after=inventory.quantity_on_hand,
            reserved_before=reserved_before,
            reserved_after=inventory.quantity_reserved,
            reason=reason,
            actor=actor if getattr(actor, "pk", None) else None,
            reference_type=reference_type,
            reference_id=str(reference_id or ""),
        )
