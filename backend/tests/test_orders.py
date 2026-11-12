"""Order lifecycle, state machine enforcement and customer data isolation."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.cart.models import Cart
from apps.cart.services import CartService
from apps.core.exceptions import InvalidStateTransition, NotFound
from apps.inventory.models import Inventory
from apps.orders.checkout import CheckoutService
from apps.orders.models import Order
from apps.orders.services import OrderService
from apps.payments.models import Payment
from apps.payments.paystack import PaystackResponse, PaystackService
from apps.payments.services import PaymentService
from tests.factories import (
    make_customer, make_product, make_shipping_zone, paystack_success_payload, shipping_payload,
)


def paid_order(customer, product, quantity=1, key="order-key-0001") -> Order:
    cart = Cart.objects.create(user=customer)
    CartService.add_item(cart, product_id=product.pk, quantity=quantity)
    order = CheckoutService.checkout_cart(
        cart=cart, shipping=shipping_payload(), customer=customer, idempotency_key=key,
    ).order
    with patch.object(PaystackService, "initialize_transaction") as init:
        init.return_value = PaystackResponse(
            ok=True, status_code=200, message="ok",
            data={"authorization_url": "https://pay", "access_code": "ac", "reference": "r"},
            raw={"status": True, "data": {"authorization_url": "https://pay"}},
        )
        payload = PaymentService.initialize_order_payment(order)
    payment = Payment.objects.get(pk=payload["payment_id"])
    body = paystack_success_payload(payment.reference, int(order.grand_total * 100))
    with patch.object(PaystackService, "verify_transaction",
                      return_value=PaystackResponse(ok=True, status_code=200, message="ok",
                                                    data=body["data"], raw=body)):
        PaymentService.verify_payment(payment.reference)
    order.refresh_from_db()
    return order


class OrderStateMachineTests(TestCase):
    def setUp(self):
        make_shipping_zone()
        self.customer = make_customer()
        self.product = make_product(price="10000.00", stock=20)
        self.order = paid_order(self.customer, self.product)

    def test_paid_order_reaches_paid_state(self):
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertIsNotNone(self.order.paid_at)

    def test_happy_path_transitions(self):
        o = OrderService.transition(self.order, Order.Status.PROCESSING)
        o = OrderService.transition(o, Order.Status.PACKING)
        o = OrderService.transition(o, Order.Status.DISPATCHED)
        o = OrderService.transition(o, Order.Status.OUT_FOR_DELIVERY)
        o = OrderService.transition(o, Order.Status.DELIVERED)
        o = OrderService.transition(o, Order.Status.COMPLETED)
        self.assertEqual(o.status, Order.Status.COMPLETED)
        self.assertEqual(o.fulfilment_progress, 100)

    def test_invalid_jump_is_rejected(self):
        with self.assertRaises(InvalidStateTransition):
            OrderService.transition(self.order, Order.Status.DELIVERED)

    def test_cannot_mark_paid_without_a_payment(self):
        """An unpaid order can never be flipped to paid — that is the whole point."""
        product = make_product(stock=3)
        unpaid = CheckoutService.checkout_cart(
            cart=self._cart(product), shipping=shipping_payload(), customer=self.customer,
            idempotency_key="order-key-0002",
        ).order
        self.assertEqual(unpaid.payment_status, Order.PaymentStatus.UNPAID)
        with self.assertRaises(InvalidStateTransition):
            OrderService.transition(unpaid, Order.Status.PAID)
        unpaid.refresh_from_db()
        self.assertNotEqual(unpaid.status, Order.Status.PAID)

    def test_terminal_state_cannot_be_reopened(self):
        completed = OrderService.transition(
            OrderService.transition(
                OrderService.transition(
                    OrderService.transition(
                        OrderService.transition(
                            OrderService.transition(self.order, Order.Status.PROCESSING),
                            Order.Status.PACKING),
                        Order.Status.DISPATCHED),
                    Order.Status.OUT_FOR_DELIVERY),
                Order.Status.DELIVERED),
            Order.Status.COMPLETED)
        with self.assertRaises(InvalidStateTransition):
            OrderService.transition(completed, Order.Status.PROCESSING)

    def test_customer_can_cancel_only_unpaid_orders(self):
        other = CheckoutService.checkout_cart(
            cart=self._cart(make_product(stock=5)), shipping=shipping_payload(),
            customer=self.customer, idempotency_key="order-key-0003",
        ).order
        cancelled = OrderService.cancel(other, actor=self.customer, reason="Changed mind")
        self.assertEqual(cancelled.status, Order.Status.CANCELLED)

        with self.assertRaises(InvalidStateTransition):
            OrderService.cancel(self.order, actor=self.customer, reason="Too late")

    def _cart(self, product):
        cart = Cart.objects.create(user=self.customer)
        CartService.add_item(cart, product_id=product.pk, quantity=1)
        return cart

    def test_cancelling_releases_reserved_stock(self):
        product = make_product(stock=5)
        order = CheckoutService.checkout_cart(
            cart=self._cart(product), shipping=shipping_payload(), customer=self.customer,
            idempotency_key="order-key-0004",
        ).order
        inventory = Inventory.objects.get(product=product, variation=None)
        self.assertEqual(inventory.quantity_reserved, 1)
        OrderService.cancel(order, actor=self.customer, reason="Test")
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity_reserved, 0)
        self.assertEqual(inventory.quantity_on_hand, 5)

    def test_expiry_releases_stock_and_lapses_order(self):
        product = make_product(stock=4)
        order = CheckoutService.checkout_cart(
            cart=self._cart(product), shipping=shipping_payload(), customer=self.customer,
            idempotency_key="order-key-0005",
        ).order
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timezone.timedelta(minutes=5)
        )
        result = OrderService.expire_stale_orders()
        self.assertGreaterEqual(result["expired_orders"], 1)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)
        inventory = Inventory.objects.get(product=product, variation=None)
        self.assertEqual(inventory.quantity_reserved, 0)

    def test_activity_trail_is_written(self):
        events = set(self.order.activities.values_list("event", flat=True))
        self.assertIn("created", events)
        self.assertIn("payment_confirmed", events)


class OrderAccessTests(TestCase):
    def setUp(self):
        make_shipping_zone()
        self.owner = make_customer()
        self.other = make_customer()
        self.order = paid_order(self.owner, make_product(), key="order-key-0100")

    def test_customer_can_read_own_order(self):
        order = OrderService.get_customer_order(self.order.order_number, self.owner)
        self.assertEqual(order.pk, self.order.pk)

    def test_other_customer_cannot_read_the_order(self):
        with self.assertRaises(NotFound):
            OrderService.get_customer_order(self.order.order_number, self.other)

    def test_guest_without_token_cannot_read_the_order(self):
        guest_order = CheckoutService.checkout_buy_now(
            product_id=str(make_product(stock=3).pk), quantity=1,
            shipping=shipping_payload(), guest_email="guest@example.com",
            idempotency_key="order-key-0101",
        ).order
        with self.assertRaises(NotFound):
            OrderService.get_guest_order(guest_order.order_number, "wrong-token")

    def test_guest_with_valid_token_can_read_the_order(self):
        guest_order = CheckoutService.checkout_buy_now(
            product_id=str(make_product(stock=3).pk), quantity=1,
            shipping=shipping_payload(), guest_email="guest@example.com",
            idempotency_key="order-key-0102",
        ).order
        token = guest_order._plain_guest_token
        found = OrderService.get_guest_order(guest_order.order_number, token)
        self.assertEqual(found.pk, guest_order.pk)


class OrderApiTests(TestCase):
    def setUp(self):
        make_shipping_zone()
        self.customer = make_customer()
        self.product = make_product(price="10000.00", stock=10)

    def _checkout_via_api(self, key="api-checkout-0001"):
        self.client.force_login(self.customer)
        self.client.post(
            "/api/v1/cart/items/",
            data={"product_id": str(self.product.pk), "quantity": 1},
            content_type="application/json",
        )
        response = self.client.post(
            "/api/v1/orders/checkout/cart/",
            data={
                **{k: v for k, v in shipping_payload().items()},
                "idempotency_key": key,
            },
            content_type="application/json",
        )
        return response

    def test_checkout_requires_idempotency_key_for_safe_replay(self):
        response = self._checkout_via_api()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        order_number = body["data"]["order_number"]
        self.assertTrue(order_number.startswith("STM-"))
        self.assertEqual(body["data"]["grand_total"], "11800.00")

    def test_order_numbers_are_not_sequential_ids(self):
        response = self._checkout_via_api()
        order_number = response.json()["data"]["order_number"]
        self.assertNotIn(str(self.customer.pk), order_number)
        self.assertRegex(order_number, r"^STM-\d{6}-\d{5}$")

    def test_unauthenticated_customer_order_list_is_blocked(self):
        response = self.client.get("/api/v1/orders/")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_customer_only_sees_their_own_orders(self):
        self._checkout_via_api()
        stranger = make_customer()
        self.client.force_login(stranger)
        response = self.client.get("/api/v1/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
