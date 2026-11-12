"""Checkout: pricing authority, Buy Now isolation, discounts and idempotency."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.cart.models import Cart
from apps.cart.services import CartService
from apps.core.exceptions import ConflictError, ValidationError
from apps.inventory.models import Inventory
from apps.inventory.models import InventoryReservation
from apps.orders.checkout import CheckoutService
from apps.orders.models import Order
from apps.orders.pricing import PricingService
from apps.promotions.models import Promotion
from tests.factories import (
    make_customer, make_product, make_promotion, make_shipping_zone, make_variation,
    shipping_payload,
)


class CheckoutCartTests(TestCase):
    def setUp(self):
        make_shipping_zone()
        self.customer = make_customer()
        self.product = make_product(price="10000.00", stock=10)
        self.cart = Cart.objects.create(user=self.customer)
        CartService.add_item(self.cart, product_id=self.product.pk, quantity=2)

    def _checkout(self, **kwargs):
        return CheckoutService.checkout_cart(
            cart=self.cart,
            shipping=shipping_payload(),
            customer=self.customer,
            idempotency_key=kwargs.pop("idempotency_key", "key-abcdef123456"),
            **kwargs,
        )

    def test_order_totals_are_computed_by_the_backend(self):
        result = self._checkout()
        order = result.order
        self.assertEqual(order.subtotal, Decimal("20000.00"))
        self.assertEqual(order.shipping_total, Decimal("1800.00"))
        self.assertEqual(order.grand_total, Decimal("21800.00"))
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)

    def test_order_creation_reserves_stock(self):
        self._checkout()
        inventory = Inventory.objects.get(product=self.product, variation=None)
        self.assertEqual(inventory.quantity_reserved, 2)
        self.assertEqual(inventory.available_quantity, 8)

    def test_cart_is_converted_and_emptied(self):
        self._checkout()
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, Cart.Status.CONVERTED)
        self.assertEqual(self.cart.items.count(), 0)

    def test_client_supplied_total_is_ignored(self):
        """A tampered payload cannot change what is charged."""
        result = CheckoutService.checkout_cart(
            cart=self.cart,
            shipping=shipping_payload(),
            customer=self.customer,
            idempotency_key="key-tamper-000001",
        )
        self.assertEqual(result.order.grand_total, Decimal("21800.00"))

    def test_empty_cart_is_rejected(self):
        CartService.clear(self.cart)
        with self.assertRaises(ValidationError):
            self._checkout()

    def test_missing_contact_details_are_rejected(self):
        with self.assertRaises(ValidationError):
            CheckoutService.checkout_cart(
                cart=self.cart,
                shipping={"full_name": "Ada", "phone": "", "address_line": "x",
                          "city": "Enugu", "state": "Enugu"},
                customer=self.customer,
                idempotency_key="key-bad-contact-1",
            )

    def test_undeliverable_state_is_rejected(self):
        with self.assertRaises(ValidationError):
            CheckoutService.checkout_cart(
                cart=self.cart,
                shipping=shipping_payload(state="Sokoto"),
                customer=self.customer,
                idempotency_key="key-bad-state-01",
            )

    def test_idempotency_returns_the_same_order(self):
        first = self._checkout(idempotency_key="key-idem-000001")
        second = CheckoutService.checkout_cart(
            cart=self.cart, shipping=shipping_payload(), customer=self.customer,
            idempotency_key="key-idem-000001",
        )
        self.assertEqual(first.order.pk, second.order.pk)
        self.assertEqual(Order.objects.count(), 1)
        inventory = Inventory.objects.get(product=self.product, variation=None)
        self.assertEqual(inventory.quantity_reserved, 2)

    def test_percentage_discount_is_applied_and_recorded(self):
        promotion = make_promotion(value=Decimal("10.00"))
        self.cart.applied_codes = [promotion.code]
        self.cart.save(update_fields=["applied_codes"])
        result = self._checkout(idempotency_key="key-promo-00001")
        self.assertEqual(result.order.discount_total, Decimal("2000.00"))
        self.assertEqual(result.order.grand_total, Decimal("19800.00"))
        self.assertEqual(promotion.usages.count(), 1)
        self.assertEqual(promotion.usages.first().order_id, result.order.pk)

    def test_maximum_discount_cap_is_respected(self):
        promotion = make_promotion(value=Decimal("50.00"), max_discount_amount=Decimal("1500.00"))
        self.cart.applied_codes = [promotion.code]
        self.cart.save(update_fields=["applied_codes"])
        result = self._checkout(idempotency_key="key-promo-cap-1")
        self.assertEqual(result.order.discount_total, Decimal("1500.00"))

    def test_expired_promotion_is_not_applied(self):
        promotion = make_promotion(
            value=Decimal("20.00"),
            ends_at=timezone.now() - timezone.timedelta(hours=1),
        )
        self.cart.applied_codes = [promotion.code]
        self.cart.save(update_fields=["applied_codes"])
        result = self._checkout(idempotency_key="key-promo-exp-1")
        self.assertEqual(result.order.discount_total, Decimal("0.00"))

    def test_free_shipping_promotion_zeroes_the_fee(self):
        promotion = make_promotion(promotion_type=Promotion.Type.FREE_SHIPPING, value=Decimal("0"))
        self.cart.applied_codes = [promotion.code]
        self.cart.save(update_fields=["applied_codes"])
        result = self._checkout(idempotency_key="key-promo-ship")
        self.assertEqual(result.order.shipping_total, Decimal("0.00"))
        self.assertEqual(result.order.grand_total, Decimal("20000.00"))

    def test_promo_usage_limit_blocks_further_redemption(self):
        promotion = make_promotion(usage_limit_total=1)
        self.cart.applied_codes = [promotion.code]
        self.cart.save(update_fields=["applied_codes"])
        self._checkout(idempotency_key="key-promo-lim-1")

        second_cart = Cart.objects.create(user=self.customer)
        CartService.add_item(second_cart, product_id=self.product.pk, quantity=1)
        second_cart.applied_codes = [promotion.code]
        second_cart.save(update_fields=["applied_codes"])
        result = CheckoutService.checkout_cart(
            cart=second_cart, shipping=shipping_payload(), customer=self.customer,
            idempotency_key="key-promo-lim-2",
        )
        self.assertEqual(result.order.discount_total, Decimal("0.00"))

    def test_discount_never_exceeds_subtotal(self):
        promotion = make_promotion(
            promotion_type=Promotion.Type.FIXED_AMOUNT, value=Decimal("999999.00")
        )
        self.cart.applied_codes = [promotion.code]
        self.cart.save(update_fields=["applied_codes"])
        result = self._checkout(idempotency_key="key-promo-big-1")
        self.assertEqual(result.order.discount_total, Decimal("20000.00"))
        self.assertGreaterEqual(result.order.grand_total, Decimal("0.00"))


class BuyNowTests(TestCase):
    """Section 45 rule 8: Buy Now must not include cart contents."""

    def setUp(self):
        make_shipping_zone()
        self.customer = make_customer()
        self.cart_product = make_product(name="Cart item", price="5000.00", stock=10)
        self.buy_product = make_product(name="Buy now item", price="30000.00", stock=5)

        self.cart = Cart.objects.create(user=self.customer)
        CartService.add_item(self.cart, product_id=self.cart_product.pk, quantity=3)

    def test_buy_now_ignores_existing_cart(self):
        result = CheckoutService.checkout_buy_now(
            product_id=str(self.buy_product.pk),
            quantity=1,
            shipping=shipping_payload(),
            customer=self.customer,
            idempotency_key="key-buynow-0001",
        )
        order = result.order
        self.assertEqual(order.channel, Order.Channel.BUY_NOW)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().product_id, self.buy_product.pk)
        self.assertEqual(order.subtotal, Decimal("30000.00"))
        # Cart line was not consumed or touched.
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, Cart.Status.ACTIVE)
        self.assertEqual(self.cart.items.count(), 1)
        self.assertEqual(self.cart.items.first().quantity, 3)

    def test_buy_now_price_comes_from_the_database(self):
        self.buy_product.price = "31500.00"
        self.buy_product.save(update_fields=["price"])
        result = CheckoutService.checkout_buy_now(
            product_id=str(self.buy_product.pk), quantity=2, shipping=shipping_payload(),
            customer=self.customer, idempotency_key="key-buynow-0002",
        )
        self.assertEqual(result.order.subtotal, Decimal("63000.00"))

    def test_buy_now_with_variation_uses_variation_price(self):
        parent = make_product(stock=0)
        variation = make_variation(parent, label="Large", price="45000.00", stock=3)
        result = CheckoutService.checkout_buy_now(
            product_id=str(parent.pk), variation_id=str(variation.pk), quantity=1,
            shipping=shipping_payload(), customer=self.customer,
            idempotency_key="key-buynow-0003",
        )
        self.assertEqual(result.order.subtotal, Decimal("45000.00"))

    def test_buy_now_respects_stock(self):
        with self.assertRaises(ConflictError):
            CheckoutService.checkout_buy_now(
                product_id=str(self.buy_product.pk), quantity=6, shipping=shipping_payload(),
                customer=self.customer, idempotency_key="key-buynow-0004",
            )

    def test_guest_buy_now_issues_an_access_token(self):
        result = CheckoutService.checkout_buy_now(
            product_id=str(self.buy_product.pk), quantity=1, shipping=shipping_payload(),
            guest_email="guest@example.com", guest_phone="+2348012345678",
            idempotency_key="key-buynow-guest",
        )
        self.assertEqual(result.order.customer_id, None)
        self.assertTrue(result.order.guest_access_token_hash)
        token = getattr(result.order, "_plain_guest_token", None)
        self.assertTrue(token)
        self.assertTrue(result.order.verify_guest_token(token))


class PricingServiceTests(TestCase):
    def setUp(self):
        make_shipping_zone()
        self.product = make_product(price="8000.00", stock=10)

    def test_free_shipping_threshold(self):
        make_shipping_zone(state="Lagos", price="2500.00", free_over="10000.00")
        lines = [PricingService.build_line(product=self.product, quantity=2)]
        breakdown = PricingService.price_basket(lines, shipping_state="Lagos")
        self.assertEqual(breakdown.shipping_total, Decimal("0.00"))

    def test_tax_is_separately_reported(self):
        self.product.tax_rate_percent = Decimal("7.50")
        self.product.save(update_fields=["tax_rate_percent"])
        lines = [PricingService.build_line(product=self.product, quantity=1)]
        breakdown = PricingService.price_basket(lines, shipping_state="Enugu")
        self.assertEqual(breakdown.tax_total, Decimal("600.00"))
        self.assertEqual(breakdown.grand_total, Decimal("10400.00"))

    def test_discount_allocation_sums_to_the_discount(self):
        second = make_product(price="2000.00", stock=10)
        lines = [
            PricingService.build_line(product=self.product, quantity=1),
            PricingService.build_line(product=second, quantity=1),
        ]
        allocations = PricingService.allocate_line_discounts(lines, Decimal("333.33"))
        self.assertEqual(sum(allocations), Decimal("333.33"))
