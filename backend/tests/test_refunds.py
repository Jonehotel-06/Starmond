"""Refund workflows: authority, caps, provider confirmation and restocking."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.core.exceptions import (
    ConflictError, InvalidStateTransition, PermissionDeniedError, ValidationError,
)
from apps.inventory.models import Inventory
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.paystack import PaystackResponse, PaystackService
from apps.refunds.models import Refund
from apps.refunds.services import RefundService
from tests.test_orders import paid_order
from tests.factories import make_customer, make_product, make_shipping_zone


def provider_refund(status="pending", refund_id=555) -> PaystackResponse:
    return PaystackResponse(
        ok=True, status_code=200, message="ok",
        data={"id": refund_id, "status": status, "transaction_reference": "ref"},
        raw={"status": True, "data": {"id": refund_id, "status": status}},
    )


class RefundTests(TestCase):
    def setUp(self):
        make_shipping_zone()
        self.customer = make_customer()
        self.product = make_product(price="10000.00", stock=10)
        self.order = paid_order(self.customer, self.product, quantity=2, key="refund-setup-1")

    def _request(self, **kwargs):
        return RefundService.request_refund(
            order=self.order,
            reason_category=Refund.Reason.DAMAGED,
            customer_note="Box arrived crushed.",
            requested_by=self.customer,
            **kwargs,
        )

    def test_customer_can_request_a_refund_on_their_paid_order(self):
        refund = self._request()
        self.assertEqual(refund.status, Refund.Status.REQUESTED)
        self.assertEqual(refund.amount_requested, Decimal("21800.00"))
        self.assertEqual(refund.order_id, self.order.pk)

    def test_refund_number_is_human_readable(self):
        refund = self._request()
        self.assertRegex(refund.refund_number, r"^RFN-\d{6}-[A-Z0-9]{6}$")

    def test_unpaid_order_cannot_be_refunded(self):
        from apps.orders.checkout import CheckoutService
        from apps.cart.models import Cart
        from apps.cart.services import CartService
        from tests.factories import shipping_payload

        cart = Cart.objects.create(user=self.customer)
        CartService.add_item(cart, product_id=self.product.pk, quantity=1)
        unpaid = CheckoutService.checkout_cart(
            cart=cart, shipping=shipping_payload(), customer=self.customer,
            idempotency_key="refund-setup-2",
        ).order
        with self.assertRaises(ConflictError):
            RefundService.request_refund(
                order=unpaid, reason_category=Refund.Reason.OTHER, requested_by=self.customer,
            )

    def test_another_customer_cannot_request_a_refund(self):
        stranger = make_customer()
        with self.assertRaises(PermissionDeniedError):
            RefundService.request_refund(
                order=self.order, reason_category=Refund.Reason.OTHER, requested_by=stranger,
            )

    def test_partial_refund_by_item_quantity(self):
        item = self.order.items.first()
        refund = self._request(items=[{"order_item_id": str(item.pk), "quantity": 1}])
        self.assertEqual(refund.refund_type, Refund.Type.PARTIAL)
        self.assertEqual(refund.amount_requested, Decimal("10000.00"))

    def test_refund_amount_cannot_exceed_paid_amount(self):
        with self.assertRaises(ValidationError):
            self._request(amount=Decimal("99999.00"))

    def test_duplicate_open_refund_is_refused(self):
        self._request()
        with self.assertRaises(ConflictError):
            self._request()

    def test_approval_requires_permission(self):
        refund = self._request()
        with self.assertRaises(PermissionDeniedError):
            RefundService.approve(refund, actor=make_customer())

    def test_approval_and_submission_do_not_complete_the_refund(self):
        refund = self._request()
        from tests.factories import make_staff

        admin = make_staff()
        refund = RefundService.approve(refund, actor=admin, restock=True)

        with patch.object(PaystackService, "refund_transaction", return_value=provider_refund("pending")):
            refund = RefundService.submit_to_provider(refund, actor=admin)

        self.assertEqual(refund.status, Refund.Status.PROCESSING)
        self.assertIsNotNone(refund.provider_refund_id)
        self.order.refresh_from_db()
        self.assertEqual(self.order.amount_refunded, Decimal("0.00"))
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_provider_confirmation_completes_the_refund(self):
        from tests.factories import make_staff

        admin = make_staff()
        refund = RefundService.approve(self._request(), actor=admin, restock=True)
        with patch.object(PaystackService, "refund_transaction", return_value=provider_refund("pending")):
            refund = RefundService.submit_to_provider(refund, actor=admin)

        with patch.object(PaystackService, "fetch_refund",
                          return_value=provider_refund("processed")):
            refund = RefundService.check_provider_status(refund, actor=admin)

        self.assertEqual(refund.status, Refund.Status.COMPLETED)
        self.assertEqual(refund.amount_refunded, Decimal("21800.00"))

        self.order.refresh_from_db()
        self.assertEqual(self.order.amount_refunded, Decimal("21800.00"))
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)

        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.REFUNDED)

        item = self.order.items.first()
        self.assertTrue(item.is_fully_refunded)

    def test_restock_returns_goods_to_sellable_stock(self):
        from tests.factories import make_staff

        admin = make_staff()
        refund = RefundService.approve(self._request(), actor=admin, restock=True)
        with patch.object(PaystackService, "refund_transaction", return_value=provider_refund("pending")):
            refund = RefundService.submit_to_provider(refund, actor=admin)
        with patch.object(PaystackService, "fetch_refund",
                          return_value=provider_refund("processed")):
            RefundService.check_provider_status(refund, actor=admin)

        inventory = Inventory.objects.get(product=self.product, variation=None)
        self.assertEqual(inventory.quantity_on_hand, 10)   # 10 - 2 sold + 2 returned
        self.assertEqual(inventory.quantity_returned, 2)

    def test_no_restock_when_staff_do_not_confirm_return(self):
        from tests.factories import make_staff

        admin = make_staff()
        refund = RefundService.approve(self._request(), actor=admin, restock=False)
        with patch.object(PaystackService, "refund_transaction", return_value=provider_refund("pending")):
            refund = RefundService.submit_to_provider(refund, actor=admin)
        with patch.object(PaystackService, "fetch_refund",
                          return_value=provider_refund("processed")):
            RefundService.check_provider_status(refund, actor=admin)
        inventory = Inventory.objects.get(product=self.product, variation=None)
        self.assertEqual(inventory.quantity_on_hand, 8)
        self.assertEqual(inventory.quantity_returned, 0)

    def test_completion_is_idempotent(self):
        from tests.factories import make_staff

        admin = make_staff()
        refund = RefundService.approve(self._request(), actor=admin)
        with patch.object(PaystackService, "refund_transaction", return_value=provider_refund("pending")):
            refund = RefundService.submit_to_provider(refund, actor=admin)
        with patch.object(PaystackService, "fetch_refund",
                          return_value=provider_refund("processed")):
            RefundService.check_provider_status(refund, actor=admin)
            RefundService.check_provider_status(
                Refund.objects.get(pk=refund.pk), actor=admin
            )
        self.order.refresh_from_db()
        self.assertEqual(self.order.amount_refunded, Decimal("21800.00"))  # not doubled

    def test_provider_failure_marks_the_refund_failed(self):
        from tests.factories import make_staff

        admin = make_staff()
        refund = RefundService.approve(self._request(), actor=admin)
        with patch.object(PaystackService, "refund_transaction", return_value=provider_refund("pending")):
            refund = RefundService.submit_to_provider(refund, actor=admin)
        with patch.object(PaystackService, "fetch_refund",
                          return_value=provider_refund("failed")):
            refund = RefundService.check_provider_status(refund, actor=admin)
        self.assertEqual(refund.status, Refund.Status.FAILED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.amount_refunded, Decimal("0.00"))

    def test_rejection_requires_a_reason_and_blocks_processing(self):
        from tests.factories import make_staff

        admin = make_staff()
        refund = self._request()
        with self.assertRaises(ValidationError):
            RefundService.reject(refund, actor=admin, reason="")
        refund = RefundService.reject(refund, actor=admin, reason="Outside policy")
        self.assertEqual(refund.status, Refund.Status.REJECTED)
        with self.assertRaises(InvalidStateTransition):
            RefundService.approve(refund, actor=admin)

    def test_cannot_submit_an_unapproved_refund(self):
        from tests.factories import make_staff

        refund = self._request()
        with self.assertRaises(InvalidStateTransition):
            RefundService.submit_to_provider(refund, actor=make_staff())

    def test_refund_cannot_exceed_amount_still_held(self):
        from tests.factories import make_staff

        admin = make_staff()
        refund = self._request()
        with self.assertRaises(ValidationError):
            RefundService.approve(refund, actor=admin, amount=Decimal("50000.00"))

    def test_reconcile_sweep_completes_pending_refunds(self):
        from tests.factories import make_staff

        admin = make_staff()
        refund = RefundService.approve(self._request(), actor=admin)
        with patch.object(PaystackService, "refund_transaction", return_value=provider_refund("pending")):
            RefundService.submit_to_provider(refund, actor=admin)
        with patch.object(PaystackService, "fetch_refund",
                          return_value=provider_refund("processed")):
            result = RefundService.reconcile_pending()
        self.assertEqual(result["completed"], 1)
