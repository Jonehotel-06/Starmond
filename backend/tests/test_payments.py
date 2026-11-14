import hashlib
import hmac
import json

from django.conf import settings
from django.test import override_settings

from apps.core.money import naira_to_kobo
from apps.orders.models import Order
from apps.payments.models import Payment, PaymentWebhookEvent

from .base import StarmondAPITestCase

WEBHOOK_SECRET = "whsec_test_123"


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha512).hexdigest()


@override_settings(PAYSTACK_SECRET_KEY="sk_test_x", PAYSTACK_WEBHOOK_SECRET=WEBHOOK_SECRET,
                   PAYSTACK_PUBLIC_KEY="pk_test_x", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PaystackPaymentTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(name="Iron", sku="IRN-1", price="12000.00", stock=6)
        self.zone, self.method = self.make_shipping("Lagos", fee="1500.00")
        self.payload = self.checkout_payload(self.product, quantity=2, shipping_method=self.method)
        response = self.client.post("/api/checkout/", self.payload, format="json")
        self.order_data = response.data["data"]
        self.order = Order.objects.get(reference=self.order_data["reference"])
        self.assertEqual(self.order.total_amount.to_eng_string(), "25500.00")

    def _initialize(self):
        self.order.refresh_from_db()
        with self.mock_paystack():
            return self.client.post("/api/payments/paystack/initialize/", {
                "order_reference": self.order.reference,
                "guest_token": self.order.guest_access_token}, format="json")

    def test_initialize_returns_authorization_url_and_records_payment(self):
        response = self._initialize()
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertTrue(data["authorization_url"].startswith("https://"))
        payment = Payment.objects.get(provider_reference=data["provider_reference"])
        self.assertEqual(payment.amount, self.order.total_amount)
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_initialize_reuses_pending_payment(self):
        r1 = self._initialize()
        r2 = self._initialize()
        self.assertEqual(r1.data["data"]["provider_reference"], r2.data["data"]["provider_reference"])
        self.assertEqual(Payment.objects.count(), 1)

    def test_verify_success_marks_order_paid_and_confirms_stock(self):
        init = self._initialize()
        provider_ref = init.data["data"]["provider_reference"]
        kobo = naira_to_kobo(self.order.total_amount)
        with self.mock_paystack(verify={"status": True, "data": {
                "status": "success", "reference": provider_ref, "amount": int(kobo),
                "currency": "NGN", "channel": "card", "id": 4242, "gateway_response": "Successful"}}):
            response = self.client.post("/api/payments/paystack/verify/", {
                "reference": provider_ref, "guest_token": self.order.guest_access_token}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.PAID)
        payment = Payment.objects.get(provider_reference=provider_ref)
        self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)
        self.assertIsNotNone(payment.verified_at)
        from apps.inventory.services import InventoryService
        inventory = InventoryService.resolve_inventory(self.product, None)
        self.assertEqual(inventory.on_hand, 4)   # 6 - 2 sold
        self.assertEqual(inventory.reserved, 0)  # reservation finalized

    def test_verify_is_idempotent(self):
        init = self._initialize()
        provider_ref = init.data["data"]["provider_reference"]
        kobo = int(naira_to_kobo(self.order.total_amount))
        verify_payload = {"status": True, "data": {"status": "success", "reference": provider_ref,
                          "amount": kobo, "currency": "NGN", "id": 1}}
        payload = {"reference": provider_ref, "guest_token": self.order.guest_access_token}
        with self.mock_paystack(verify=verify_payload):
            self.client.post("/api/payments/paystack/verify/", payload, format="json")
            second = self.client.post("/api/payments/paystack/verify/", payload, format="json")
        self.assertEqual(second.status_code, 200)
        from apps.inventory.services import InventoryService
        inventory = InventoryService.resolve_inventory(self.product, None)
        self.assertEqual(inventory.on_hand, 4)  # stock deducted once

    def test_verify_wrong_amount_rejected(self):
        init = self._initialize()
        provider_ref = init.data["data"]["provider_reference"]
        with self.mock_paystack(verify={"status": True, "data": {
                "status": "success", "reference": provider_ref, "amount": 100,
                "currency": "NGN", "id": 9}}):
            response = self.client.post("/api/payments/paystack/verify/", {
                "reference": provider_ref, "guest_token": self.order.guest_access_token}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["error"]["code"], "amount_mismatch")
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_verify_wrong_currency_rejected(self):
        init = self._initialize()
        provider_ref = init.data["data"]["provider_reference"]
        kobo = int(naira_to_kobo(self.order.total_amount))
        with self.mock_paystack(verify={"status": True, "data": {
                "status": "success", "reference": provider_ref, "amount": kobo,
                "currency": "GHS", "id": 10}}):
            response = self.client.post("/api/payments/paystack/verify/", {
                "reference": provider_ref, "guest_token": self.order.guest_access_token}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["error"]["code"], "currency_mismatch")

    def test_verify_failed_transaction_marks_failed(self):
        init = self._initialize()
        provider_ref = init.data["data"]["provider_reference"]
        with self.mock_paystack(verify={"status": True, "data": {
                "status": "failed", "reference": provider_ref, "amount": 0,
                "gateway_response": "Declined by bank"}}):
            response = self.client.post("/api/payments/paystack/verify/", {
                "reference": provider_ref, "guest_token": self.order.guest_access_token}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAYMENT_FAILED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)

    def test_verify_unknown_reference_404(self):
        with self.mock_paystack():
            response = self.client.post("/api/payments/paystack/verify/", {"reference": "NOPE"}, format="json")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------ webhook
    def _webhook(self, event, secret=WEBHOOK_SECRET, sign=True):
        body = json.dumps(event).encode()
        headers = {}
        if sign:
            headers["HTTP_X_PAYSTACK_SIGNATURE"] = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
        return self.client.post("/api/payments/paystack/webhook/", data=body,
                                content_type="application/json", **headers)

    def _success_event(self, provider_ref, amount_kobo=None, event_id=1):
        return {
            "event": "charge.success",
            "data": {
                "id": event_id, "reference": provider_ref,
                "amount": int(amount_kobo or naira_to_kobo(self.order.total_amount)),
                "currency": "NGN", "status": "success", "channel": "card",
                "metadata": {"order_reference": self.order.reference},
            },
        }

    def test_webhook_invalid_signature_rejected(self):
        init = self._initialize()
        event = self._success_event(init.data["data"]["provider_reference"])
        response = self._webhook(event, secret="wrong-secret")
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_webhook_missing_signature_rejected(self):
        init = self._initialize()
        event = self._success_event(init.data["data"]["provider_reference"])
        response = self._webhook(event, sign=False)
        self.assertEqual(response.status_code, 400)

    def test_webhook_success_confirms_order(self):
        init = self._initialize()
        provider_ref = init.data["data"]["provider_reference"]
        with self.mock_paystack(verify={"status": True, "data": {
                "status": "success", "reference": provider_ref,
                "amount": int(naira_to_kobo(self.order.total_amount)), "currency": "NGN", "id": 77}}):
            response = self._webhook(self._success_event(provider_ref))
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertTrue(PaymentWebhookEvent.objects.filter(processed=True).exists())

    def test_webhook_duplicate_delivery_processed_once(self):
        init = self._initialize()
        provider_ref = init.data["data"]["provider_reference"]
        event = self._success_event(provider_ref, event_id=555)
        with self.mock_paystack(verify={"status": True, "data": {
                "status": "success", "reference": provider_ref,
                "amount": int(naira_to_kobo(self.order.total_amount)), "currency": "NGN", "id": 77}}):
            r1 = self._webhook(event)
            r2 = self._webhook(event)  # Paystack retry
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)
        from apps.inventory.services import InventoryService
        inventory = InventoryService.resolve_inventory(self.product, None)
        self.assertEqual(inventory.on_hand, 4)  # deducted once only

    def test_redirect_without_verification_does_not_mark_paid(self):
        # Customer "returns from Paystack" but no verification: order must stay pending.
        self._initialize()
        response = self.client.get(f"/api/orders/{self.order.reference}/?token={self.order.guest_access_token or ''}")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_cannot_initialize_payment_for_expired_order(self):
        from django.utils import timezone
        from datetime import timedelta
        Order.objects.filter(pk=self.order.pk).update(expires_at=timezone.now() - timedelta(minutes=5))
        with self.mock_paystack():
            response = self.client.post("/api/payments/paystack/initialize/", {
                "order_reference": self.order.reference,
                "guest_token": self.order.guest_access_token}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["error"]["code"], "order_expired")

    def test_already_paid_order_cannot_initialize_again(self):
        init = self._initialize()
        provider_ref = init.data["data"]["provider_reference"]
        with self.mock_paystack(verify={"status": True, "data": {
                "status": "success", "reference": provider_ref,
                "amount": int(naira_to_kobo(self.order.total_amount)), "currency": "NGN", "id": 78}}):
            self.client.post("/api/payments/paystack/verify/", {
                "reference": provider_ref, "guest_token": self.order.guest_access_token}, format="json")
            response = self.client.post("/api/payments/paystack/initialize/", {
                "order_reference": self.order.reference,
                "guest_token": self.order.guest_access_token}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "order_already_paid")
