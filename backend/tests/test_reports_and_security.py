"""
Financial integrity, reporting accuracy, SEO surfaces and API security.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.paystack import PaystackResponse, PaystackService
from apps.payments.services import PaymentService
from apps.refunds.models import Refund
from apps.refunds.services import RefundService
from apps.reports.services import DateRange, ReportService
from apps.seo.services import SEOService
from tests.factories import (
    make_category, make_customer, make_product, make_settings, make_shipping_zone, make_staff,
)
from tests.test_orders import paid_order


class FinancialIntegrityTests(TestCase):
    def setUp(self):
        make_settings()
        make_shipping_zone()
        self.customer = make_customer()
        self.product = make_product(price="10000.00", stock=50)
        self.period = DateRange.from_request()

    def test_unpaid_orders_are_not_counted_as_revenue(self):
        from apps.cart.models import Cart
        from apps.cart.services import CartService
        from apps.orders.checkout import CheckoutService
        from tests.factories import shipping_payload

        cart = Cart.objects.create(user=self.customer)
        CartService.add_item(cart, product_id=self.product.pk, quantity=3)
        CheckoutService.checkout_cart(
            cart=cart, shipping=shipping_payload(), customer=self.customer,
            idempotency_key="fin-unpaid-0001",
        )
        summary = ReportService.sales_summary(self.period)
        self.assertEqual(summary["sales"]["total_collected"], "0.00")
        self.assertEqual(summary["sales"]["net_sales"], "0.00")
        self.assertEqual(summary["orders"]["total_placed"], 1)
        self.assertEqual(summary["orders"]["paid"], 0)

    def test_paid_order_revenue_is_counted_once(self):
        paid_order(self.customer, self.product, quantity=2, key="fin-paid-0001")
        summary = ReportService.sales_summary(self.period)
        self.assertEqual(summary["sales"]["total_collected"], "21800.00")
        self.assertEqual(summary["payments"]["successful_count"], 1)
        self.assertEqual(summary["orders"]["paid"], 1)

    def test_duplicate_settlement_does_not_double_count(self):
        order = paid_order(self.customer, self.product, quantity=1, key="fin-dup-0001")
        payment = Payment.objects.get(order=order)
        body = {
            "data": {
                "reference": payment.reference, "amount": int(order.grand_total * 100),
                "currency": "NGN", "status": "success", "channel": "card",
                "gateway_response": "Successful", "customer": {"email": "x@y.com"},
                "authorization": {},
            }
        }
        with patch.object(PaystackService, "verify_transaction",
                          return_value=PaystackResponse(ok=True, status_code=200, message="ok",
                                                        data=body["data"], raw=body)):
            PaymentService.verify_payment(payment.reference)

        summary = ReportService.sales_summary(self.period)
        self.assertEqual(summary["payments"]["successful_count"], 1)
        self.assertEqual(summary["sales"]["total_collected"], "11800.00")

    def test_refunds_reduce_net_sales(self):
        order = paid_order(self.customer, self.product, quantity=1, key="fin-refund-0001")
        admin = make_staff()
        refund = RefundService.request_refund(
            order=order, reason_category=Refund.Reason.CHANGED_MIND, requested_by=self.customer,
        )
        refund = RefundService.approve(refund, actor=admin)
        with patch.object(PaystackService, "refund_transaction",
                          return_value=PaystackResponse(
                              ok=True, status_code=200, message="ok",
                              data={"id": 1, "status": "pending"}, raw={"data": {"id": 1}})):
            refund = RefundService.submit_to_provider(refund, actor=admin)
        with patch.object(PaystackService, "fetch_refund",
                          return_value=PaystackResponse(
                              ok=True, status_code=200, message="ok",
                              data={"id": 1, "status": "processed"}, raw={"data": {"id": 1}})):
            RefundService.check_provider_status(refund, actor=admin)

        summary = ReportService.sales_summary(self.period)
        self.assertEqual(summary["sales"]["total_collected"], "11800.00")
        self.assertEqual(summary["sales"]["refunds"], "11800.00")
        self.assertEqual(summary["sales"]["net_sales"], "0.00")

    def test_integrity_check_flags_a_mismatched_order(self):
        order = paid_order(self.customer, self.product, quantity=1, key="fin-mismatch-1")
        Order.objects.filter(pk=order.pk).update(amount_paid=Decimal("99999.00"))
        checks = ReportService.integrity_checks(self.period)
        self.assertFalse(checks["healthy"])
        self.assertEqual(checks["discrepancy_count"], 1)

    def test_healthy_books_pass_the_integrity_check(self):
        paid_order(self.customer, self.product, quantity=1, key="fin-healthy-1")
        checks = ReportService.integrity_checks(self.period)
        self.assertTrue(checks["healthy"])

    def test_average_order_value(self):
        paid_order(self.customer, self.product, quantity=1, key="fin-aov-0001")
        paid_order(self.customer, self.product, quantity=2, key="fin-aov-0002")
        summary = ReportService.sales_summary(self.period)
        # 11800 and 21800 → mean 16800
        self.assertEqual(summary["averages"]["average_order_value"], "16800.00")

    def test_report_exports_render(self):
        paid_order(self.customer, self.product, quantity=1, key="fin-export-1")
        self.assertIn("STARMOND", ReportService.export_csv(self.period))
        self.assertTrue(ReportService.export_xlsx(self.period).startswith(b"PK"))
        self.assertTrue(ReportService.export_pdf(self.period).startswith(b"%PDF"))


class ReportingApiTests(TestCase):
    def setUp(self):
        make_settings()
        make_shipping_zone()
        self.admin = make_staff()

    def test_export_requires_staff(self):
        response = self.client.get("/api/v1/reports/export/csv/")
        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_export(self):
        self.client.force_login(make_customer())
        response = self.client.get("/api/v1/reports/export/csv/")
        self.assertIn(response.status_code, {401, 403})

    def test_staff_export_returns_a_file(self):
        self.client.force_login(self.admin)
        response = self.client.get("/api/v1/reports/export/csv/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_export_is_audited(self):
        from apps.audit.models import AuditLog

        self.client.force_login(self.admin)
        self.client.get("/api/v1/reports/export/xlsx/")
        self.assertTrue(
            AuditLog.objects.filter(action="export", actor=self.admin).exists()
        )


class SEOTests(TestCase):
    def setUp(self):
        make_settings()
        self.category = make_category(name="Laptops", published=True)
        self.product = make_product(name="Studio Laptop", category=self.category)

    def test_sitemap_includes_public_product_and_category(self):
        xml = SEOService.sitemap_xml()
        self.assertIn(self.product.absolute_path, xml)
        self.assertIn(self.category.absolute_path, xml)
        self.assertIn("<urlset", xml)

    def test_sitemap_excludes_drafts_and_noindex(self):
        draft = make_product(published=False)
        noindex = make_product()
        noindex.noindex = True
        noindex.save(update_fields=["noindex"])
        xml = SEOService.sitemap_xml()
        self.assertNotIn(draft.absolute_path, xml)
        self.assertNotIn(noindex.absolute_path, xml)

    def test_sitemap_excludes_private_paths(self):
        xml = SEOService.sitemap_xml()
        self.assertNotIn("/api/", xml)
        self.assertNotIn("/checkout", xml)

    def test_robots_txt_disallows_private_areas(self):
        robots = SEOService.robots_txt()
        self.assertIn("Disallow: /api/", robots)
        self.assertIn("Disallow: /admin/", robots)
        self.assertIn("Sitemap:", robots)

    def test_robots_txt_endpoint_is_public(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])

    def test_sitemap_endpoint_is_public(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])

    def test_product_metadata_has_canonical_and_structured_data(self):
        meta = SEOService.product_metadata(self.product)
        self.assertIn("/product/", meta["canonical"])
        self.assertEqual(meta["structured_data"]["@type"], "Product")
        self.assertEqual(meta["structured_data"]["sku"], self.product.sku)
        self.assertEqual(meta["og"]["type"], "product")

    def test_category_metadata_is_complete(self):
        meta = SEOService.category_metadata(self.category)
        self.assertEqual(meta["robots"], "index,follow")
        self.assertIn("breadcrumbs", meta)

    def test_metadata_endpoint_returns_noindex_for_private_paths(self):
        response = self.client.get("/api/v1/seo/metadata/?path=/checkout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["robots"], "noindex,nofollow")

    def test_organization_structured_data(self):
        data = SEOService.organisation_structured_data()
        self.assertEqual(data["@type"], "Organization")
        self.assertIn("url", data)


class ApiSecurityTests(TestCase):
    def setUp(self):
        make_settings()
        make_shipping_zone()
        self.customer = make_customer()
        self.other = make_customer()
        self.product = make_product(stock=10)

    def test_cart_cannot_be_used_to_set_a_price(self):
        response = self.client.post(
            "/api/v1/cart/items/",
            data={"product_id": str(self.product.pk), "quantity": 1, "unit_price": "1.00",
                  "price": "1.00", "line_total": "1.00"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["subtotal"], "10000.00")

    def test_customer_cannot_read_another_customers_address(self):
        from apps.customers.models import Address

        address = Address.objects.create(
            user=self.other, recipient_name="Other", phone="+2348012345678",
            street_address="1 Other Street", city="Enugu", state="Enugu",
        )
        self.client.force_login(self.customer)
        response = self.client.get(f"/api/v1/customers/addresses/{address.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_wishlist_is_per_customer(self):
        self.client.force_login(self.customer)
        self.client.post(
            "/api/v1/customers/wishlist/",
            data={"product_id": str(self.product.pk)}, content_type="application/json",
        )
        self.client.force_login(self.other)
        response = self.client.get("/api/v1/customers/wishlist/")
        self.assertEqual(response.json()["count"], 0)

    def test_staff_product_endpoints_block_customers(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            "/api/v1/products/admin/",
            data={"name": "Hack", "category_id": str(self.product.category_id),
                  "price": "1.00", "sku": "HACK-1"},
            content_type="application/json",
        )
        self.assertIn(response.status_code, {401, 403})

    def test_staff_inventory_endpoints_block_customers(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            "/api/v1/inventory/receive/",
            data={"inventory_id": "00000000-0000-0000-0000-000000000000", "quantity": 999},
            content_type="application/json",
        )
        self.assertIn(response.status_code, {401, 403, 404})

    def test_refund_admin_endpoints_block_customers(self):
        self.client.force_login(self.customer)
        response = self.client.get("/api/v1/refunds/admin/")
        self.assertIn(response.status_code, {401, 403})

    def test_error_envelope_never_leaks_internals(self):
        response = self.client.get("/api/v1/products/does-not-exist/")
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertNotIn("Traceback", str(body))
        self.assertIn("code", body["error"])

    def test_request_id_is_returned_for_support(self):
        response = self.client.get("/api/v1/products/")
        self.assertIn("X-Request-ID", response)

    def test_search_is_throttled_scope_not_unbounded(self):
        response = self.client.get("/api/v1/products/?page_size=100000")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()["results"]), 100)
