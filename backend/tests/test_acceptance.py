"""
End-to-end acceptance test mirroring Section 46.

Administrator creates the catalogue → customer buys and pays → stock moves →
administrator fulfils → customer tracks → order completes, with financial and
inventory records agreeing at every step.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import PublishableModel
from apps.inventory.models import Inventory
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.paystack import PaystackResponse, PaystackService
from apps.payments.services import PaymentService
from apps.products.models import Product
from apps.reports.services import DateRange, ReportService
from apps.shipping.models import Shipment
from tests.factories import (
    make_customer, make_product, make_settings, make_shipping_zone, make_staff, uniq,
)


class FullWorkflowAcceptanceTests(TestCase):
    def setUp(self):
        make_settings()
        make_shipping_zone(state="Enugu", price="1800.00")
        self.admin = make_staff(superuser=True)
        self.client.force_login(self.admin)

    def test_complete_purchase_workflow(self):
        # ---- 1. Administrator logs in and creates a category ---------------
        response = self.client.post(
            "/api/v1/catalogue/admin/",
            data={"name": "Consumer Electronics", "status": "published", "is_featured": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        category_id = response.json()["data"]["id"]

        # ---- 2. …adds a subcategory ---------------------------------------
        response = self.client.post(
            "/api/v1/catalogue/admin/",
            data={"name": "Audio", "parent_id": category_id, "status": "published"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        subcategory_id = response.json()["data"]["id"]
        self.assertEqual(response.json()["data"]["depth"], 1)

        # ---- 3. …adds a product with price and stock ----------------------
        sku = f"ACC-{uniq()}".upper()[:20]
        response = self.client.post(
            "/api/v1/products/admin/",
            data={
                "name": "Studio Headphones",
                "category_id": subcategory_id,
                "price": "45000.00",
                "compare_at_price": "52000.00",
                "sku": sku,
                "opening_stock": 10,
                "status": "published",
                "short_description": "Over-ear studio monitoring headphones.",
                "meta_title": "Studio Headphones — STARMOND",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        product_id = response.json()["data"]["id"]
        product = Product.objects.get(pk=product_id)
        self.assertEqual(product.status, PublishableModel.Status.PUBLISHED)
        self.assertEqual(product.sku, sku)

        inventory = Inventory.objects.get(product=product, variation=None)
        self.assertEqual(inventory.quantity_on_hand, 10)

        # ---- 4. Product appears on the public site with SEO --------------
        self.client.logout()
        response = self.client.get(f"/api/v1/products/{product.slug}/")
        self.assertEqual(response.status_code, 200)
        public = response.json()["data"]
        self.assertEqual(public["price"], "45000.00")
        self.assertEqual(public["availability"]["available_quantity"], 10)
        self.assertIn("structured_data", public["seo"])
        self.assertEqual(public["seo"]["structured_data"]["@type"], "Product")

        listing = self.client.get("/api/v1/products/")
        self.assertGreaterEqual(listing.json()["count"], 1)

        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(product.absolute_path, sitemap)

        # ---- 5. Customer browses, adds to cart, checks out ----------------
        customer = make_customer(email="buyer@example.com")
        self.client.force_login(customer)

        add = self.client.post(
            "/api/v1/cart/items/",
            data={"product_id": str(product.pk), "quantity": 2},
            content_type="application/json",
        )
        self.assertEqual(add.status_code, 201)
        self.assertEqual(add.json()["data"]["subtotal"], "90000.00")

        quote = self.client.post(
            "/api/v1/shipping/quote/",
            data={"state": "Enugu", "city": "Enugu", "subtotal": "90000.00"},
            content_type="application/json",
        )
        self.assertEqual(quote.status_code, 200)
        self.assertEqual(quote.json()["data"]["quote"]["fee"], "1800.00")

        checkout = self.client.post(
            "/api/v1/orders/checkout/cart/",
            data={
                "full_name": "Chinelo Eze",
                "phone": "+2348033334444",
                "address_line": "5 Zik Avenue",
                "city": "Enugu",
                "state": "Enugu",
                "lga": "Enugu North",
                "idempotency_key": "acceptance-checkout-0001",
            },
            content_type="application/json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.content)
        order_number = checkout.json()["data"]["order_number"]
        self.assertEqual(checkout.json()["data"]["grand_total"], "91800.00")

        order = Order.objects.get(order_number=order_number)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)

        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity_reserved, 2)
        self.assertEqual(inventory.available_quantity, 8)

        # ---- 6. Customer pays through Paystack ---------------------------
        with patch.object(PaystackService, "initialize_transaction") as init:
            init.return_value = PaystackResponse(
                ok=True, status_code=200, message="ok",
                data={"authorization_url": "https://checkout.paystack.com/xyz",
                      "access_code": "xyz", "reference": "r"},
                raw={"status": True, "data": {"authorization_url": "https://checkout.paystack.com/xyz"}},
            )
            pay = self.client.post(
                "/api/v1/payments/initialize/",
                data={"order_number": order_number}, content_type="application/json",
            )
        self.assertEqual(pay.status_code, 200, pay.content)
        reference = pay.json()["data"]["reference"]
        self.assertNotIn("sk_", str(pay.json()))

        # ---- 7. Backend verifies payment independently -------------------
        payment = Payment.objects.get(reference=reference)
        verify_body = {
            "data": {
                "reference": reference,
                "amount": int(order.grand_total * 100),
                "currency": "NGN",
                "status": "success",
                "channel": "card",
                "gateway_response": "Successful",
                "paid_at": "2026-11-12T10:00:00+01:00",
                "customer": {"email": customer.email, "customer_code": "CUS_1"},
                "authorization": {"authorization_code": "AUTH_1", "last4": "4081"},
            }
        }
        with patch.object(PaystackService, "verify_transaction",
                          return_value=PaystackResponse(ok=True, status_code=200, message="ok",
                                                        data=verify_body["data"], raw=verify_body)):
            verified = self.client.get(f"/api/v1/payments/verify/?reference={reference}")
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json()["data"]["payment_status"], "paid")

        # ---- 8. Order confirmed, inventory updated, receipt generated ----
        order.refresh_from_db()
        payment.refresh_from_db()
        inventory.refresh_from_db()

        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.amount_paid, Decimal("91800.00"))
        self.assertTrue(payment.is_verified)
        self.assertEqual(inventory.quantity_on_hand, 8)
        self.assertEqual(inventory.quantity_reserved, 0)
        self.assertEqual(inventory.quantity_sold, 2)

        receipt = self.client.get(f"/api/v1/orders/{order_number}/receipt/")
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.json()["data"]["amount_paid"], "91800.00")
        self.assertTrue(receipt.json()["data"]["receipt_number"].startswith("RCP-"))

        # A confirmation notification was queued for the customer.
        self.assertTrue(customer.notifications.filter(notification_type="payment").exists())

        # ---- 9. Administrator processes the delivery ---------------------
        self.client.force_login(self.admin)

        processing = self.client.post(
            f"/api/v1/orders/admin/{order_number}/transition/",
            data={"status": "processing"}, content_type="application/json",
        )
        self.assertEqual(processing.status_code, 200, processing.content)

        shipment_response = self.client.post(
            f"/api/v1/shipping/admin/shipments/{order_number}/",
            data={"carrier": "STARMOND Logistics"}, content_type="application/json",
        )
        self.assertEqual(shipment_response.status_code, 201, shipment_response.content)
        tracking = shipment_response.json()["data"]["tracking_reference"]
        self.assertTrue(tracking.startswith("STM"))

        for status, description in (
            ("dispatched", "Collected by courier"),
            ("out_for_delivery", "With rider in Enugu"),
            ("delivered", "Signed for by customer"),
        ):
            response = self.client.post(
                f"/api/v1/shipping/admin/shipments/{tracking}/events/",
                data={"status": status, "description": description,
                      "location": "Enugu"},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, response.content)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertIsNotNone(order.delivered_at)

        # ---- 10. Customer tracks the order -------------------------------
        self.client.force_login(customer)
        track = self.client.get(f"/api/v1/orders/{order_number}/track/")
        self.assertEqual(track.status_code, 200)
        tracking_payload = track.json()["data"]["tracking"]
        self.assertEqual(tracking_payload["tracking_reference"], tracking)
        events = [e["status"] for e in tracking_payload["events"]]
        self.assertIn("delivered", events)
        self.assertGreaterEqual(len(events), 3)

        # ---- 11. Order completed -----------------------------------------
        self.client.force_login(self.admin)
        completed = self.client.post(
            f"/api/v1/orders/admin/{order_number}/transition/",
            data={"status": "completed"}, content_type="application/json",
        )
        self.assertEqual(completed.status_code, 200, completed.content)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(order.fulfilment_progress, 100)

        # ---- 12. Financial and inventory records agree -------------------
        summary = ReportService.sales_summary(DateRange.from_request())
        self.assertEqual(summary["sales"]["total_collected"], "91800.00")
        self.assertEqual(summary["sales"]["net_sales"], "91800.00")
        self.assertEqual(summary["orders"]["paid"], 1)
        self.assertEqual(summary["orders"]["completed"], 1)
        self.assertTrue(summary["data_integrity"]["healthy"])

        inventory.refresh_from_db()
        self.assertEqual(
            inventory.quantity_on_hand,
            10 - inventory.quantity_sold,
        )
        self.assertTrue(
            all(
                report["consistent"]
                for report in [
                    __import__("apps.inventory.services", fromlist=["InventoryService"])
                    .InventoryService.reconcile(inventory)
                ]
            )
        )

        product.refresh_from_db()
        self.assertEqual(product.sold_count, 2)
        self.assertEqual(product.rating_count, 0)  # no fake reviews

        audit_actions = set(
            __import__("apps.audit.models", fromlist=["AuditLog"]).AuditLog.objects
            .values_list("action", flat=True)
        )
        self.assertIn("payment_verified", audit_actions)
        self.assertIn("order_state_changed", audit_actions)


class ReviewAcceptanceTests(TestCase):
    def setUp(self):
        make_settings()
        make_shipping_zone()
        self.customer = make_customer()
        self.product = make_product(stock=5)

    def test_verified_purchase_badge_comes_from_a_real_order(self):
        from apps.reviews.services import ReviewService
        from tests.test_orders import paid_order

        paid_order(self.customer, self.product, key="review-acceptance-1")
        review = ReviewService.create_review(
            user=self.customer, product=self.product, rating=5,
            comment="Excellent build quality and fast delivery.",
        )
        self.assertTrue(review.is_verified_purchase)
        self.assertFalse(review.is_approved)  # held for moderation

        from apps.reviews.models import Review
        from tests.factories import make_staff

        ReviewService.moderate(review, approved=True, moderator=make_staff())
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_count, 1)
        self.assertEqual(self.product.rating_average, Decimal("5.00"))

        public = self.client.get(f"/api/v1/reviews/product/{self.product.slug}/")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.json()["count"], 1)

    def test_unverified_customer_cannot_claim_a_verified_badge(self):
        from apps.reviews.services import ReviewService

        review = ReviewService.create_review(
            user=self.customer, product=self.product, rating=3,
            comment="Looks fine but I never bought it here.",
        )
        self.assertFalse(review.is_verified_purchase)

    def test_duplicate_review_is_blocked(self):
        from apps.core.exceptions import ConflictError
        from apps.reviews.services import ReviewService

        ReviewService.create_review(
            user=self.customer, product=self.product, rating=4,
            comment="Solid product overall, happy with it.",
        )
        with self.assertRaises(ConflictError):
            ReviewService.create_review(
                user=self.customer, product=self.product, rating=5,
                comment="Trying to review twice on the same product.",
            )

    def test_unapproved_review_is_not_public(self):
        from apps.reviews.services import ReviewService

        ReviewService.create_review(
            user=self.customer, product=self.product, rating=1,
            comment="Awaiting moderation, should not be visible.",
        )
        response = self.client.get(f"/api/v1/reviews/product/{self.product.slug}/")
        self.assertEqual(response.json()["count"], 0)
