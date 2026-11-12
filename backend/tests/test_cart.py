"""Cart behaviour: duplicate prevention, quantity validation and merging."""
from __future__ import annotations

from django.test import TestCase

from apps.cart.models import Cart
from apps.cart.services import CartService
from apps.core.exceptions import ConflictError, ValidationError
from apps.inventory.models import Inventory
from apps.inventory.services import InventoryService
from tests.factories import make_customer, make_product, make_shipping_zone, make_variation


class CartTests(TestCase):
    def setUp(self):
        make_shipping_zone()
        self.product = make_product(price="10000.00", stock=10)
        self.cart = Cart.objects.create()

    def test_add_item_uses_server_price(self):
        item = CartService.add_item(self.cart, product_id=self.product.pk, quantity=2)
        self.assertEqual(item.quantity, 2)
        summary = CartService.summary(self.cart, shipping_state="Enugu")
        self.assertEqual(summary["subtotal"], "20000.00")

    def test_adding_same_product_increments_existing_line(self):
        CartService.add_item(self.cart, product_id=self.product.pk, quantity=1)
        CartService.add_item(self.cart, product_id=self.product.pk, quantity=2)
        self.assertEqual(self.cart.items.count(), 1)
        self.assertEqual(self.cart.items.first().quantity, 3)

    def test_quantity_beyond_stock_is_rejected(self):
        with self.assertRaises(ConflictError):
            CartService.add_item(self.cart, product_id=self.product.pk, quantity=11)
        self.assertEqual(self.cart.items.count(), 0)

    def test_zero_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            CartService.add_item(self.cart, product_id=self.product.pk, quantity=0)

    def test_negative_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            CartService.add_item(self.cart, product_id=self.product.pk, quantity=-5)

    def test_unpublished_product_cannot_be_added(self):
        draft = make_product(published=False)
        with self.assertRaises(ValidationError):
            CartService.add_item(self.cart, product_id=draft.pk, quantity=1)

    def test_variation_based_product_requires_a_variation(self):
        parent = make_product()
        make_variation(parent, label="XL", stock=4)
        with self.assertRaises(ValidationError):
            CartService.add_item(self.cart, product_id=parent.pk, quantity=1)

    def test_variation_stock_is_validated(self):
        parent = make_product(stock=0)
        variation = make_variation(parent, label="XS", stock=2)
        with self.assertRaises(ConflictError):
            CartService.add_item(
                self.cart, product_id=parent.pk, variation_id=variation.pk, quantity=3
            )
        item = CartService.add_item(
            self.cart, product_id=parent.pk, variation_id=variation.pk, quantity=2
        )
        self.assertEqual(item.quantity, 2)

    def test_update_quantity_respects_stock(self):
        item = CartService.add_item(self.cart, product_id=self.product.pk, quantity=1)
        with self.assertRaises(ConflictError):
            CartService.update_item(self.cart, item_id=str(item.pk), quantity=11)
        CartService.update_item(self.cart, item_id=str(item.pk), quantity=5)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)

    def test_remove_and_clear(self):
        item = CartService.add_item(self.cart, product_id=self.product.pk, quantity=1)
        CartService.remove_item(self.cart, item_id=str(item.pk))
        self.assertEqual(self.cart.items.count(), 0)
        CartService.add_item(self.cart, product_id=self.product.pk, quantity=1)
        CartService.clear(self.cart)
        self.assertEqual(self.cart.items.count(), 0)

    def test_cart_summary_recalculates_price_when_catalogue_changes(self):
        CartService.add_item(self.cart, product_id=self.product.pk, quantity=1)
        self.product.price = "12500.00"
        self.product.save(update_fields=["price"])
        summary = CartService.summary(self.cart, shipping_state="Enugu")
        self.assertEqual(summary["subtotal"], "12500.00")

    def test_shipping_fee_is_added_by_backend(self):
        CartService.add_item(self.cart, product_id=self.product.pk, quantity=1)
        summary = CartService.summary(self.cart, shipping_state="Enugu")
        self.assertEqual(summary["shipping_total"], "1800.00")
        self.assertEqual(summary["grand_total"], "11800.00")

    def test_delivery_refused_for_uncovered_state(self):
        CartService.add_item(self.cart, product_id=self.product.pk, quantity=1)
        summary = CartService.summary(self.cart, shipping_state="Sokoto")
        self.assertFalse(summary["shipping_eligible"])

    def test_guest_cart_merge_combines_quantities(self):
        from django.test import RequestFactory
        from django.contrib.sessions.backends.db import SessionStore

        user = make_customer()
        request = RequestFactory().get("/")
        request.session = SessionStore()
        request.user = type("Anon", (), {"is_authenticated": False})()

        guest_cart = CartService.get_for_request(request)
        CartService.add_item(guest_cart, product_id=self.product.pk, quantity=2)

        customer_cart = Cart.objects.create(user=user)
        CartService.add_item(customer_cart, product_id=self.product.pk, quantity=1)

        merged_cart, info = CartService.merge_guest_cart(request, user)
        self.assertEqual(info["merged_lines"], 1)
        self.assertEqual(merged_cart.items.get(product=self.product).quantity, 3)
        guest_cart.refresh_from_db()
        self.assertEqual(guest_cart.status, Cart.Status.MERGED)

    def test_merge_caps_at_available_stock(self):
        from django.test import RequestFactory
        from django.contrib.sessions.backends.db import SessionStore

        user = make_customer()
        request = RequestFactory().get("/")
        request.session = SessionStore()
        request.user = type("Anon", (), {"is_authenticated": False})()

        guest_cart = CartService.get_for_request(request)
        CartService.add_item(guest_cart, product_id=self.product.pk, quantity=4)

        customer_cart = Cart.objects.create(user=user)
        CartService.add_item(customer_cart, product_id=self.product.pk, quantity=5)

        # Stock shrinks to 6 before the merge.
        inventory = Inventory.objects.get(product=self.product, variation=None)
        InventoryService.adjust_stock(inventory=inventory, new_quantity=6, reason="Shrink")

        merged_cart, _ = CartService.merge_guest_cart(request, user)
        self.assertEqual(merged_cart.items.get(product=self.product).quantity, 6)

    def test_gift_of_a_promo_code_is_capped(self):
        for code in ("AAA", "BBB", "CCC"):
            CartService.apply_code(self.cart, code)
        with self.assertRaises(ValidationError):
            CartService.apply_code(self.cart, "DDD")
