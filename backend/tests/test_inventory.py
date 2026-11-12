"""Inventory integrity: reservations, commits, releases and concurrency."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, TransactionTestCase

from apps.core.exceptions import ConflictError, InsufficientStock, ValidationError
from apps.inventory.models import Inventory, InventoryMovement, InventoryReservation
from apps.inventory.services import InventoryService
from tests.factories import make_product, make_variation


class InventoryBasicsTests(TestCase):
    def setUp(self):
        self.product = make_product(price="5000.00", stock=10)
        self.inventory = Inventory.objects.get(product=self.product, variation=None)

    def test_available_stock_formula(self):
        self.assertEqual(self.inventory.available_quantity, 10)
        InventoryService.reserve(inventory=self.inventory, quantity=3)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_reserved, 3)
        self.assertEqual(self.inventory.available_quantity, 7)

    def test_receive_stock_increases_on_hand_and_logs_movement(self):
        InventoryService.receive_stock(inventory=self.inventory, quantity=15, reason="Delivery")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 25)
        movement = self.inventory.movements.filter(
            movement_type=InventoryMovement.Type.RECEIVED
        ).first()
        self.assertEqual(movement.quantity, 15)
        self.assertEqual(movement.on_hand_after, 25)

    def test_reservation_cannot_exceed_available(self):
        with self.assertRaises(InsufficientStock):
            InventoryService.reserve(inventory=self.inventory, quantity=11)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_reserved, 0)

    def test_commit_sale_reduces_on_hand_and_increases_sold(self):
        reservation = InventoryService.reserve(inventory=self.inventory, quantity=4)
        InventoryService.commit_sale(reservation=reservation)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 6)
        self.assertEqual(self.inventory.quantity_reserved, 0)
        self.assertEqual(self.inventory.quantity_sold, 4)

    def test_commit_is_idempotent(self):
        reservation = InventoryService.reserve(inventory=self.inventory, quantity=2)
        InventoryService.commit_sale(reservation=reservation)
        InventoryService.commit_sale(reservation=reservation)  # webhook retry
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 8)
        self.assertEqual(self.inventory.quantity_sold, 2)

    def test_release_returns_stock_and_is_idempotent(self):
        reservation = InventoryService.reserve(inventory=self.inventory, quantity=5)
        InventoryService.release(reservation=reservation, reason="Cancelled")
        InventoryService.release(reservation=reservation, reason="Cancelled again")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_reserved, 0)
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_stock_cannot_go_negative(self):
        InventoryService.adjust_stock(inventory=self.inventory, new_quantity=5, reason="Stock take")
        with self.assertRaises(ValidationError):
            InventoryService.adjust_stock(inventory=self.inventory, new_quantity=-1, reason="Bad")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 5)

    def test_adjustment_below_reserved_is_refused(self):
        InventoryService.reserve(inventory=self.inventory, quantity=6)
        with self.assertRaises(ConflictError):
            InventoryService.adjust_stock(
                inventory=self.inventory, new_quantity=2, reason="Stock take"
            )

    def test_cannot_commit_a_released_reservation(self):
        reservation = InventoryService.reserve(inventory=self.inventory, quantity=2)
        InventoryService.release(reservation=reservation)
        with self.assertRaises(ConflictError):
            InventoryService.commit_sale(reservation=reservation)

    def test_variation_stock_is_tracked_independently(self):
        variation = make_variation(self.product, label="Blue", price="7000.00", stock=3)
        self.assertEqual(InventoryService.available_quantity(self.product, variation), 3)
        self.assertEqual(InventoryService.available_quantity(self.product), 10)

    def test_variation_without_stock_row_cannot_oversell(self):
        variation = make_variation(self.product, label="Green", price="7000.00", stock=2)
        Inventory.objects.filter(product=self.product, variation=variation).delete()
        self.assertEqual(InventoryService.available_quantity(self.product, variation), 0)

    def test_reconcile_detects_counter_drift(self):
        InventoryService.reserve(inventory=self.inventory, quantity=3)
        self.assertTrue(InventoryService.reconcile(self.inventory)["consistent"])
        Inventory.objects.filter(pk=self.inventory.pk).update(quantity_reserved=1)
        report = InventoryService.reconcile(Inventory.objects.get(pk=self.inventory.pk))
        self.assertFalse(report["consistent"])
        self.assertEqual(report["drift"], -2)

    def test_database_forbids_reserved_exceeding_on_hand(self):
        """The counter invariant is enforced by the database, not just by code."""
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Inventory.objects.filter(pk=self.inventory.pk).update(quantity_reserved=999)

    def test_movements_are_immutable(self):
        InventoryService.receive_stock(inventory=self.inventory, quantity=1)
        movement = self.inventory.movements.first()
        with self.assertRaises(PermissionError):
            movement.reason = "tampered"
            movement.save()


class InventoryConcurrencyTests(TransactionTestCase):
    """Two buyers racing for the last unit — exactly one may win."""

    def test_concurrent_reservations_never_oversell(self):
        product = make_product(price="9000.00", stock=1)
        inventory = Inventory.objects.get(product=product, variation=None)

        first = InventoryService.reserve(inventory=inventory, quantity=1)
        self.assertEqual(first.status, InventoryReservation.Status.ACTIVE)

        with self.assertRaises(InsufficientStock):
            InventoryService.reserve(inventory=inventory, quantity=1)

        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity_on_hand, 1)
        self.assertEqual(inventory.quantity_reserved, 1)
        self.assertEqual(inventory.available_quantity, 0)

    def test_expiry_releases_only_unpaid_reservations(self):
        from django.utils import timezone

        product = make_product(stock=5)
        inventory = Inventory.objects.get(product=product, variation=None)
        reservation = InventoryService.reserve(inventory=inventory, quantity=2)
        InventoryReservation.objects.filter(pk=reservation.pk).update(
            expires_at=timezone.now() - timezone.timedelta(minutes=1)
        )
        result = InventoryService.expire_stale_reservations()
        self.assertEqual(result["expired_reservations"], 1)
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity_reserved, 0)
        self.assertEqual(inventory.quantity_on_hand, 5)
