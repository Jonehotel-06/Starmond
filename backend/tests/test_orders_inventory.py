from decimal import Decimal

from django.test import override_settings

from apps.core.constants import Perm
from apps.inventory.models import Inventory, InventoryMovement
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.refunds.models import Refund

from .base import StarmondAPITestCase


def _pay_order(testcase, order, product_qty=None):
    """Initialize + verify an order through the mocked Paystack flow."""
    from apps.core.money import naira_to_kobo
    order.refresh_from_db()
    with testcase.mock_paystack():
        init = testcase.client.post("/api/payments/paystack/initialize/",
                                    {"order_reference": order.reference,
                                     "guest_token": order.guest_access_token}, format="json")
    provider_ref = init.data["data"]["provider_reference"]
    with testcase.mock_paystack(verify={"status": True, "data": {
            "status": "success", "reference": provider_ref,
            "amount": int(naira_to_kobo(order.total_amount)), "currency": "NGN", "id": 31}}):
        testcase.client.post("/api/payments/paystack/verify/",
                             {"reference": provider_ref, "guest_token": order.guest_access_token}, format="json")
    order.refresh_from_db()
    return order


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InventoryTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(name="Breaker 32A", sku="BRK-32", price="9000.00", stock=3)
        self.zone, self.method = self.make_shipping("Lagos", fee="1000.00")

    def _inventory(self):
        return Inventory.objects.get(product=self.product, variation__isnull=True)

    def test_reservation_lifecycle(self):
        payload = self.checkout_payload(self.product, quantity=2, shipping_method=self.method)
        self.client.post("/api/checkout/", payload, format="json")
        inv = self._inventory()
        self.assertEqual((inv.on_hand, inv.reserved, inv.available), (3, 2, 1))
        order = Order.objects.first()
        _pay_order(self, order)
        inv.refresh_from_db()
        self.assertEqual((inv.on_hand, inv.reserved, inv.available), (1, 0, 1))
        types = list(InventoryMovement.objects.filter(inventory=inv).order_by("created_at").values_list("movement_type", flat=True))
        self.assertIn("reserved", types)
        self.assertIn("sold", types)

    def test_oversell_prevented_sequential(self):
        for _ in range(3):
            payload = self.checkout_payload(self.product, quantity=1, shipping_method=self.method)
            response = self.client.post("/api/checkout/", payload, format="json")
            self.assertEqual(response.status_code, 201)
        payload = self.checkout_payload(self.product, quantity=1, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "stock_unavailable")
        inv = self._inventory()
        self.assertEqual(inv.available, 0)
        self.assertGreaterEqual(inv.on_hand, inv.reserved)

    def test_negative_inventory_blocked_by_constraint(self):
        from django.db import IntegrityError, transaction
        inv = self._inventory()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Inventory.objects.filter(pk=inv.pk).update(on_hand=-1)

    def test_cancel_releases_reservation(self):
        payload = self.checkout_payload(self.product, quantity=3, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        order = Order.objects.get(reference=response.data["data"]["reference"])
        self.assertEqual(self._inventory().available, 0)
        # guest cancel via access token
        cancel = self.client.post(f"/api/orders/{order.reference}/", {"token": order.guest_access_token}, format="json")
        self.assertEqual(cancel.status_code, 200, cancel.data)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self._inventory().available, 3)

    def test_reservation_expiry_task(self):
        from django.utils import timezone
        from datetime import timedelta
        payload = self.checkout_payload(self.product, quantity=2, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        order = Order.objects.get(reference=response.data["data"]["reference"])
        Order.objects.filter(pk=order.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        from apps.orders.tasks import expire_stale_pending_orders
        expired = expire_stale_pending_orders()
        self.assertEqual(expired, 1)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)
        self.assertEqual(self._inventory().available, 3)

    def test_staff_adjustment_requires_reason(self):
        staff = self.make_staff(perms=[Perm.INVENTORY_MANAGE, Perm.INVENTORY_VIEW])
        self.client.force_authenticate(staff)
        inv = self._inventory()
        response = self.client.post(f"/api/inventory/{inv.pk}/adjust/", {"delta": -1, "reason": ""}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post(f"/api/inventory/{inv.pk}/adjust/", {"delta": -1, "reason": "Damaged unit"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        inv.refresh_from_db()
        self.assertEqual(inv.on_hand, 2)
        movement = InventoryMovement.objects.filter(inventory=inv, movement_type="adjustment").first()
        self.assertEqual(movement.reason, "Damaged unit")

    def test_out_of_stock_status_syncs(self):
        payload = self.checkout_payload(self.product, quantity=3, shipping_method=self.method)
        self.client.post("/api/checkout/", payload, format="json")
        order = Order.objects.first()
        _pay_order(self, order)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, "out_of_stock")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", PAYSTACK_SECRET_KEY="sk_test_x", PAYSTACK_WEBHOOK_SECRET="whsec_x")
class OrderLifecycleTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(name="Blender", sku="BLD-1", price="35000.00", stock=5)
        self.zone, self.method = self.make_shipping("Lagos", fee="3000.00")
        self.manager = self.make_staff(perms=[Perm.ORDERS_VIEW, Perm.ORDERS_MANAGE, Perm.ORDERS_FULFIL, Perm.FINANCE_VIEW, Perm.FINANCE_MANAGE, Perm.REFUNDS_MANAGE])

    def _paid_order(self):
        payload = self.checkout_payload(self.product, quantity=1, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        order = Order.objects.get(reference=response.data["data"]["reference"])
        return _pay_order(self, order)

    def test_fulfilment_flow_and_invalid_transition(self):
        order = self._paid_order()
        self.client.force_authenticate(self.manager)
        for status_code in ("processing", "packed", "shipped", "out_for_delivery", "delivered", "completed"):
            response = self.client.post(f"/api/orders/admin/{order.reference}/status/",
                                        {"status": status_code, "note": f"moved to {status_code}"}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            order.refresh_from_db()
            self.assertEqual(order.status, status_code)
        # invalid jump from completed back to shipped
        response = self.client.post(f"/api/orders/admin/{order.reference}/status/", {"status": "shipped"}, format="json")
        self.assertEqual(response.status_code, 409)

    def test_staff_cannot_set_financial_statuses(self):
        order = self._paid_order()
        self.client.force_authenticate(self.manager)
        response = self.client.post(f"/api/orders/admin/{order.reference}/status/", {"status": "paid"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "protected_status")

    def test_paid_order_cannot_be_cancelled(self):
        order = self._paid_order()
        self.client.force_authenticate(self.manager)
        response = self.client.post(f"/api/orders/admin/{order.reference}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "paid_order_cancel")

    def test_receipt_contains_real_payment_records(self):
        order = self._paid_order()
        self.client.force_authenticate(self.manager)
        response = self.client.get(f"/api/orders/admin/{order.reference}/receipt/")
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(data["order"]["reference"], order.reference)
        self.assertEqual(len(data["payments"]), 1)
        self.assertEqual(data["payments"][0]["status"], "successful")
        self.assertEqual(data["invoice_number"], f"INV-{order.reference}")

    def test_refund_request_approve_and_restock(self):
        order = self._paid_order()
        customer_order = order
        # staff-assisted refund request (customer endpoint requires ownership; use service directly for guest order)
        from apps.refunds.services import RefundService
        refund = RefundService.request_refund(order, requester=None, reason="Damaged on arrival",
                                              amount=order.total_amount, restock=True, staff_created=True)
        self.assertEqual(refund.status, Refund.Status.REQUESTED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUND_REQUESTED)

        self.client.force_authenticate(self.manager)
        with self.mock_paystack(refund={"status": True, "data": {"id": 909, "status": "processed"}}):
            response = self.client.post(f"/api/refunds/admin/{refund.pk}/approve/", {
                "approved_amount": str(order.total_amount), "notes": "Approved per policy"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        refund.refresh_from_db()
        self.assertEqual(refund.status, Refund.Status.SUCCESSFUL)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.status, Payment.Status.REFUNDED)
        inv = Inventory.objects.get(product=self.product, variation__isnull=True)
        self.assertEqual(inv.on_hand, 5)  # 5 - 1 sold + 1 restocked
        self.assertEqual(inv.reserved, 0)

    def test_partial_refund(self):
        order = self._paid_order()
        from apps.refunds.services import RefundService
        refund = RefundService.request_refund(order, requester=None, reason="Missing accessory",
                                              amount=Decimal("5000.00"), staff_created=True)
        self.client.force_authenticate(self.manager)
        with self.mock_paystack(refund={"status": True, "data": {"id": 910, "status": "pending"}}):
            response = self.client.post(f"/api/refunds/admin/{refund.pk}/approve/", {"approved_amount": "5000.00"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        refund.refresh_from_db()
        self.assertEqual(refund.status, Refund.Status.PROCESSING)  # provider not final yet
        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.Status.PARTIALLY_REFUNDED)
        # confirm final provider outcome
        with self.mock_paystack(request_side_effect=lambda m, p, **k: {"status": True, "data": {"id": 910, "status": "processed"}}):
            response = self.client.post(f"/api/refunds/admin/{refund.pk}/check-status/")
        refund.refresh_from_db()
        self.assertEqual(refund.status, Refund.Status.SUCCESSFUL)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PARTIALLY_REFUNDED)
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.status, Payment.Status.PARTIALLY_REFUNDED)

    def test_refund_exceeding_payment_rejected(self):
        order = self._paid_order()
        from apps.refunds.services import RefundService
        from apps.core.exceptions import ServiceError
        with self.assertRaises(ServiceError):
            RefundService.request_refund(order, requester=None, reason="x", amount=Decimal("999999.00"), staff_created=True)

    def test_guest_order_lookup_and_private_access(self):
        payload = self.checkout_payload(self.product, quantity=1, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        reference = response.data["data"]["reference"]
        # wrong email cannot retrieve
        lookup = self.client.post("/api/orders/lookup/", {"reference": reference, "email": "wrong@example.com"}, format="json")
        self.assertEqual(lookup.status_code, 404)
        lookup = self.client.post("/api/orders/lookup/", {"reference": reference, "email": "ada@example.com"}, format="json")
        self.assertEqual(lookup.status_code, 200, lookup.data)
        token = lookup.data["data"]["token"]
        detail = self.client.get(f"/api/orders/{reference}/", {"token": token})
        self.assertEqual(detail.status_code, 200)
        # no token -> 403
        detail = self.client.get(f"/api/orders/{reference}/")
        self.assertEqual(detail.status_code, 403)
