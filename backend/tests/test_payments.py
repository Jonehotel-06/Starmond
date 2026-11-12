"""
Payments: initialisation, verification, amount/currency validation, webhook
signature checks, duplicate delivery and replay protection.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.cart.models import Cart
from apps.cart.services import CartService
from apps.core.exceptions import ConflictError, PaymentError
from apps.inventory.models import Inventory
from apps.orders.checkout import CheckoutService
from apps.orders.models import Order
from apps.payments.models import Payment, PaymentWebhookEvent
from apps.payments.paystack import PaystackResponse, PaystackService
from apps.payments.services import PaymentService
from tests.factories import (
    make_customer, make_product, make_shipping_zone, paystack_success_payload, shipping_payload,
)


def ok_response(payload: dict) -> PaystackResponse:
    return PaystackResponse(ok=True, status_code=200, message="ok",
                            data=payload.get("data", {}), raw=payload)


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()


class PaymentTestCase(TestCase):
    def setUp(self):
        make_shipping_zone()
        self.customer = make_customer()
        product = make_product(price="10000.00", stock=10)
        cart = Cart.objects.create(user=self.customer)
        CartService.add_item(cart, product_id=product.pk, quantity=2)
        self.order = CheckoutService.checkout_cart(
            cart=cart, shipping=shipping_payload(), customer=self.customer,
            idempotency_key="key-payment-setup",
        ).order
        self.product = product

    def _initialise(self):
        with patch.object(PaystackService, "initialize_transaction") as init:
            init.return_value = ok_response({
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.paystack.com/abc123",
                    "access_code": "abc123",
                    "reference": "placeholder",
                },
            })
            payload = PaymentService.initialize_order_payment(self.order)
        payment = Payment.objects.get(pk=payload["payment_id"])
        return payment, payload


class PaymentInitialisationTests(PaymentTestCase):
    def test_initialisation_creates_pending_payment(self):
        payment, payload = self._initialise()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, Decimal("21800.00"))
        self.assertEqual(payment.amount_kobo, 2180000)
        self.assertIn("authorization_url", payload)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_secret_key_is_never_returned(self):
        _payment, payload = self._initialise()
        serialised = json.dumps(payload)
        self.assertNotIn(settings.PAYSTACK_SECRET_KEY, serialised)
        self.assertIn("public_key", payload)

    def test_paid_order_cannot_be_initialised_again(self):
        payment, _ = self._initialise()
        payment.status = Payment.Status.SUCCESS
        payment.is_verified = True
        payment.save()
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.save(update_fields=["payment_status"])
        with self.assertRaises(ConflictError):
            PaymentService.initialize_order_payment(self.order)

    def test_second_initialisation_reuses_the_open_attempt(self):
        first, payload1 = self._initialise()
        with patch.object(PaystackService, "initialize_transaction") as init:
            payload2 = PaymentService.initialize_order_payment(self.order)
            init.assert_not_called()
        self.assertEqual(payload1["payment_id"], payload2["payment_id"])
        self.assertTrue(payload2["reused_existing_attempt"])
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)

    def test_live_keys_are_refused_outside_live_mode(self):
        with self.settings(PAYSTACK_SECRET_KEY="sk_live_abc", PAYSTACK_MODE="test"):
            with self.assertRaises(PaymentError):
                PaystackService.assert_credential_mode()


class PaymentVerificationTests(PaymentTestCase):
    def test_successful_verification_settles_the_order(self):
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 2180000)
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)):
            result = PaymentService.verify_payment(payment.reference)

        self.assertTrue(result.is_successful)
        self.assertTrue(result.is_verified)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.amount_paid, Decimal("21800.00"))

    def test_successful_payment_commits_inventory(self):
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 2180000)
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)):
            PaymentService.verify_payment(payment.reference)
        inventory = Inventory.objects.get(product=self.product, variation=None)
        self.assertEqual(inventory.quantity_on_hand, 8)
        self.assertEqual(inventory.quantity_reserved, 0)
        self.assertEqual(inventory.quantity_sold, 2)

    def test_underpayment_is_refused(self):
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 100000)  # ₦1,000 instead of ₦21,800
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)):
            with self.assertRaises(PaymentError):
                PaymentService.verify_payment(payment.reference)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)

    def test_currency_mismatch_is_refused(self):
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 2180000, currency="USD")
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)):
            with self.assertRaises(PaymentError):
                PaymentService.verify_payment(payment.reference)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_failed_transaction_does_not_pay_the_order(self):
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 2180000, status="failed")
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)):
            with self.assertRaises(PaymentError):
                PaymentService.verify_payment(payment.reference)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)

    def test_verification_is_idempotent(self):
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 2180000)
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)) as verify:
            PaymentService.verify_payment(payment.reference)
            PaymentService.verify_payment(payment.reference)
            self.assertEqual(verify.call_count, 1)  # second call short-circuits
        self.order.refresh_from_db()
        self.assertEqual(self.order.amount_paid, Decimal("21800.00"))
        inventory = Inventory.objects.get(product=self.product, variation=None)
        self.assertEqual(inventory.quantity_on_hand, 8)

    def test_unknown_reference_is_rejected(self):
        from apps.core.exceptions import NotFound

        with self.assertRaises(NotFound):
            PaymentService.verify_payment("STM-DOES-NOT-EXIST")


class WebhookTests(PaymentTestCase):
    def _post_webhook(self, event: dict, secret: str | None = None, signature: str | None = None):
        body = json.dumps(event).encode()
        sig = signature if signature is not None else sign(body, secret or settings.PAYSTACK_WEBHOOK_SECRET)
        return self.client.post(
            "/api/v1/payments/webhook/paystack/", data=body,
            content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=sig,
        )

    def test_invalid_signature_is_rejected(self):
        payment, _ = self._initialise()
        response = self._post_webhook(
            {"event": "charge.success", "data": {"reference": payment.reference, "id": 1}},
            signature="deadbeef",
        )
        self.assertEqual(response.status_code, 401)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertTrue(
            PaymentWebhookEvent.objects.filter(signature_valid=False, order=None).exists()
            or PaymentWebhookEvent.objects.filter(
                processing_status=PaymentWebhookEvent.ProcessingStatus.REJECTED
            ).exists()
        )

    def test_valid_webhook_settles_payment(self):
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 2180000)
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)):
            response = self._post_webhook({
                "event": "charge.success",
                "data": {"reference": payment.reference, "id": 302961},
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "settled")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_duplicate_webhook_delivery_is_ignored(self):
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 2180000)
        event = {"event": "charge.success", "data": {"reference": payment.reference, "id": 302961}}
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)) as verify:
            first = self._post_webhook(event)
            second = self._post_webhook(event)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["status"], "duplicate")
            self.assertEqual(verify.call_count, 1)

        self.order.refresh_from_db()
        self.assertEqual(self.order.amount_paid, Decimal("21800.00"))
        inventory = Inventory.objects.get(product=self.product, variation=None)
        self.assertEqual(inventory.quantity_on_hand, 8)
        self.assertEqual(inventory.quantity_sold, 2)

    def test_webhook_for_unknown_reference_is_rejected_gracefully(self):
        response = self._post_webhook({
            "event": "charge.success", "data": {"reference": "STM-UNKNOWN-1", "id": 999},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unknown_reference")

    def test_webhook_does_not_trust_payload_amount(self):
        """
        Even a signed webhook must be re-verified: the body claims success but
        Paystack reports a different amount on verification.
        """
        payment, _ = self._initialise()
        body = paystack_success_payload(payment.reference, 50000)  # ₦500
        with patch.object(PaystackService, "verify_transaction", return_value=ok_response(body)):
            response = self._post_webhook({
                "event": "charge.success",
                "data": {"reference": payment.reference, "id": 111,
                         "amount": 2180000, "status": "success"},
            })
        self.assertEqual(response.json()["status"], "failed")
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_unsigned_webhook_is_rejected_at_the_signature_layer(self):
        body = json.dumps({"event": "charge.success", "data": {"reference": "x"}}).encode()
        self.assertFalse(PaystackService.verify_webhook_signature(body, ""))

    def test_signature_computation_matches_paystack_scheme(self):
        body = b'{"event":"charge.success"}'
        self.assertEqual(
            PaystackService.compute_signature(body),
            hmac.new(
                settings.PAYSTACK_WEBHOOK_SECRET.encode(), body, hashlib.sha512
            ).hexdigest(),
        )
