from decimal import Decimal

from django.test import override_settings

from apps.core.constants import Perm
from apps.orders.models import Order

from .base import StarmondAPITestCase
from .test_orders_inventory import _pay_order


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", PAYSTACK_SECRET_KEY="sk_test_x", PAYSTACK_WEBHOOK_SECRET="whsec_x")
class DashboardReportTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(name="Rice Cooker", sku="RIC-1", price="30000.00", stock=8)
        self.zone, self.method = self.make_shipping("Lagos", fee="2000.00")
        self.owner = self.make_owner()

    def _create_order(self, qty=1):
        payload = self.checkout_payload(self.product, quantity=qty, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        return Order.objects.get(reference=response.data["data"]["reference"])

    def test_revenue_counts_only_verified_payments_once(self):
        paid_order = self._create_order(qty=2)
        _pay_order(self, paid_order)          # 60000 + 2000 = 62000
        pending_order = self._create_order()  # pending — must NOT count
        failed = self._create_order()
        from apps.core.money import naira_to_kobo
        failed.refresh_from_db()
        with self.mock_paystack():
            init = self.client.post("/api/payments/paystack/initialize/", {
                "order_reference": failed.reference, "guest_token": failed.guest_access_token}, format="json")
        with self.mock_paystack(verify={"status": True, "data": {
                "status": "failed", "reference": init.data["data"]["provider_reference"], "amount": 0}}):
            self.client.post("/api/payments/paystack/verify/", {
                "reference": init.data["data"]["provider_reference"],
                "guest_token": failed.guest_access_token}, format="json")

        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/dashboard/overview/", {"range": "today"})
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(data["financials"]["collected_revenue"], "62000.00")
        self.assertEqual(data["financials"]["orders_created"], 3)
        self.assertEqual(data["financials"]["orders_paid"], 1)
        self.assertEqual(data["financials"]["payments_failed"], 1)
        self.assertEqual(data["financials"]["orders_awaiting_payment"], 1)
        self.assertEqual(data["financials"]["average_order_value"], "62000.00")

    def test_sales_report_export_csv(self):
        order = self._create_order()
        _pay_order(self, order)
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/reports/sales/", {"range": "today", "format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("SUMMARY", response.content.decode())

    def test_orders_report_export_xlsx_and_pdf(self):
        self._create_order()
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/reports/orders/", {"range": "today", "format": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        response = self.client.get("/api/reports/orders/", {"range": "today", "format": "pdf"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_best_sellers_and_category_report(self):
        order = self._create_order(qty=3)
        _pay_order(self, order)
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/reports/products/", {"range": "today"})
        rows = response.data["data"]
        self.assertEqual(rows[0]["sku"], "RIC-1")
        self.assertEqual(rows[0]["units"], 3)
        response = self.client.get("/api/reports/categories/", {"range": "today"})
        self.assertEqual(response.data["data"][0]["category"], self.product.category.name)

    def test_accountant_sees_finance_not_products_management(self):
        order = self._create_order()
        _pay_order(self, order)
        accountant = self.make_staff(email="acc2@example.com",
                                     perms=[Perm.FINANCE_VIEW, Perm.REPORTS_VIEW, Perm.DASHBOARD_VIEW], role_name="Acc2")
        self.client.force_authenticate(accountant)
        self.assertEqual(self.client.get("/api/reports/payments/").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard/overview/").status_code, 200)
        response = self.client.post("/api/products/admin/", {
            "name": "Hack", "sku": "HCK", "category": self.product.category.pk,
            "regular_price": "1.00"}, format="json")
        self.assertEqual(response.status_code, 403)
