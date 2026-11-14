"""Concurrency protection for inventory.

True parallel oversell testing requires MySQL row locks (SELECT ... FOR
UPDATE); on SQLite (dev/test fallback) FOR UPDATE is a no-op, so the threaded
test is skipped there and the logical guarantee is verified sequentially.
The MySQL path is exercised in CI/staging where DB_ENGINE=mysql.
"""
import threading
from unittest import skipIf

from django.conf import settings
from django.db import connection, transaction
from django.test import TransactionTestCase

from apps.inventory.models import Inventory
from apps.orders.models import Order

from .base import StarmondAPITestCase


@skipIf(getattr(settings, "DB_ENGINE", "mysql") != "mysql",
        "Thread-level FOR UPDATE test requires MySQL (SQLite ignores row locks).")
class MySQLConcurrencyTest(TransactionTestCase):
    def test_parallel_checkout_cannot_oversell(self):
        from .base import StarmondAPITestCase as Base
        helper = Base()
        helper.setUp()
        product = helper.make_product(name="Limited", sku="LTD-1", price="5000.00", stock=5)
        zone, method = helper.make_shipping("Lagos", fee="1000.00")
        results = []

        def buy():
            from rest_framework.test import APIClient
            client = APIClient()
            payload = helper.checkout_payload(product, quantity=1, shipping_method=method)
            response = client.post("/api/checkout/", payload, format="json")
            results.append(response.status_code)
            connection.close()

        threads = [threading.Thread(target=buy) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        successes = results.count(201)
        self.assertEqual(successes, 5)  # exactly stock count
        inv = Inventory.objects.get(product=product, variation__isnull=True)
        self.assertEqual(inv.reserved, 5)
        self.assertEqual(inv.available, 0)
        self.assertGreaterEqual(inv.on_hand, inv.reserved)


class SequentialStockGuardTests(StarmondAPITestCase):
    """Logical oversell protection verified on any backend."""

    def test_reservation_checks_available_not_on_hand(self):
        from apps.inventory.services import InventoryService
        from apps.core.exceptions import StockUnavailableError
        product = self.make_product(name="Guard", sku="GRD-1", price="1000.00", stock=2)
        inv = InventoryService.resolve_inventory(product, None)
        InventoryService.reserve(inv, 2, reason="first")
        inv.refresh_from_db()
        self.assertEqual(inv.on_hand, 2)
        with self.assertRaises(StockUnavailableError):
            InventoryService.reserve(inv, 1, reason="second")  # available=0 although on_hand=2

    def test_release_then_rereserve(self):
        from apps.inventory.services import InventoryService
        product = self.make_product(name="Guard2", sku="GRD-2", price="1000.00", stock=3)
        inv = InventoryService.resolve_inventory(product, None)
        InventoryService.reserve(inv, 3, reason="hold")
        inv.refresh_from_db()
        self.assertEqual(inv.available, 0)
        InventoryService.release(inv, 3, reason="expired")
        inv.refresh_from_db()
        self.assertEqual(inv.available, 3)
        InventoryService.reserve(inv, 3, reason="re-hold")
        inv.refresh_from_db()
        self.assertEqual(inv.available, 0)
