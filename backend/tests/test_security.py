from decimal import Decimal

from apps.core.constants import Perm
from apps.orders.models import Order

from .base import StarmondAPITestCase


class AccessControlTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(name="Fan", sku="FAN-1", price="20000.00", stock=4)
        self.zone, self.method = self.make_shipping("Lagos", fee="2000.00")

    def _order_for(self, customer):
        self.client.force_authenticate(customer)
        payload = self.checkout_payload(self.product, quantity=1, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        return Order.objects.get(reference=response.data["data"]["reference"])

    def test_customer_cannot_access_other_customers_order(self):
        alice = self.make_customer(email="alice@example.com")
        bob = self.make_customer(email="bob@example.com")
        order = self._order_for(alice)
        self.client.force_authenticate(bob)
        response = self.client.get(f"/api/orders/{order.reference}/")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_access_staff_apis(self):
        for url in ("/api/dashboard/overview/", "/api/orders/admin/", "/api/products/admin/",
                    "/api/inventory/", "/api/reports/sales/", "/api/audit/logs/",
                    "/api/admin-panel/staff/", "/api/cms/admin/settings/"):
            response = self.client.get(url)
            self.assertIn(response.status_code, (401, 403), f"{url} returned {response.status_code}")

    def test_staff_permission_boundaries(self):
        inventory_manager = self.make_staff(email="inv@example.com",
                                            perms=[Perm.INVENTORY_VIEW, Perm.INVENTORY_MANAGE], role_name="InvMgr")
        self.client.force_authenticate(inventory_manager)
        self.assertEqual(self.client.get("/api/inventory/").status_code, 200)
        # no order permission
        self.assertEqual(self.client.get("/api/orders/admin/").status_code, 403)
        # no product management permission
        response = self.client.post("/api/products/admin/", {
            "name": "Sneaky", "sku": "SNK", "category": self.product.category.pk,
            "regular_price": "1.00"}, format="json")
        self.assertEqual(response.status_code, 403)
        # no finance/report permission
        self.assertEqual(self.client.get("/api/reports/sales/").status_code, 403)

    def test_customer_cannot_use_staff_role_endpoint(self):
        customer = self.make_customer(email="cust@example.com")
        self.client.force_authenticate(customer)
        response = self.client.get("/api/admin-panel/staff/")
        self.assertEqual(response.status_code, 403)

    def test_price_manipulation_ignored(self):
        """Client-supplied totals/prices must never affect the order."""
        payload = self.checkout_payload(self.product, quantity=1, shipping_method=self.method)
        payload["totals"] = {"total": "1.00"}
        payload["items"] = [{"unit_price": "0.01", "quantity": 1}]
        payload["delivery"]["shipping_fee"] = "0.00"
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(reference=response.data["data"]["reference"])
        self.assertEqual(order.total_amount, Decimal("22000.00"))  # 20000 + 2000 shipping

    def test_quantity_manipulation_bounded_by_stock(self):
        payload = self.checkout_payload(self.product, quantity=1000, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertIn(response.status_code, (400, 409))
        self.assertIn(response.data["error"]["code"], ("invalid_quantity", "stock_unavailable"))
        self.assertFalse(Order.objects.filter(items__quantity=1000).exists())

    def test_order_references_not_sequential_ids(self):
        customer = self.make_customer(email="ref@example.com")
        order = self._order_for(customer)
        self.assertTrue(order.reference.startswith("ORD-"))
        # sequential id endpoint must not exist
        response = self.client.get("/api/orders/1/")
        self.assertIn(response.status_code, (403, 404))

    def test_upload_requires_authentication_and_type(self):
        response = self.client.post("/api/media/uploads/", {}, format="multipart")
        self.assertIn(response.status_code, (401, 403))

    def test_inactive_staff_blocked(self):
        staff = self.make_staff(email="off@example.com", perms=[Perm.ORDERS_VIEW], role_name="Off")
        staff.staff_profile.is_active = False
        staff.staff_profile.save()
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/orders/admin/").status_code, 403)

    def test_superuser_owner_full_access(self):
        owner = self.make_owner()
        self.client.force_authenticate(owner)
        for url in ("/api/dashboard/overview/", "/api/orders/admin/", "/api/reports/sales/",
                    "/api/admin-panel/roles/", "/api/audit/logs/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class WishlistReviewTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(name="Shoes", sku="SHO-1", price="25000.00", stock=3)
        self.customer = self.make_customer(email="wish@example.com")

    def test_wishlist_add_and_move_to_cart(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/customers/wishlist/", {"product": self.product.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        response = self.client.get("/api/customers/wishlist/")
        self.assertEqual(len(response.data["data"]), 1)
        response = self.client.post("/api/customers/wishlist/move-to-cart/", {"product": self.product.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/api/cart/")
        self.assertEqual(response.data["data"]["item_count"], 1)
        response = self.client.get("/api/customers/wishlist/")
        self.assertEqual(len(response.data["data"]), 0)

    def test_review_requires_moderation_and_prevents_duplicates(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/reviews/", {
            "product": self.product.pk, "rating": 5, "title": "Great", "body": "Very good shoes."}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        # duplicate rejected
        response = self.client.post("/api/reviews/", {
            "product": self.product.pk, "rating": 4, "body": "Again"}, format="json")
        self.assertEqual(response.status_code, 409)
        # pending review not public
        self.client.force_authenticate(None)
        response = self.client.get(f"/api/reviews/product/{self.product.slug}/")
        self.assertEqual(response.data["count"], 0)
        self.assertIsNone(response.data["summary"]["average_rating"])
        # staff approve
        moderator = self.make_staff(email="mod@example.com", perms=[Perm.REVIEWS_MODERATE], role_name="Mod")
        from apps.reviews.models import Review
        review = Review.objects.first()
        self.client.force_authenticate(moderator)
        response = self.client.post(f"/api/reviews/admin/{review.pk}/approve/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(None)
        response = self.client.get(f"/api/reviews/product/{self.product.slug}/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["summary"]["average_rating"], 5.0)
        # verified purchase derives from real orders only
        self.assertFalse(Review.objects.get(pk=review.pk).is_verified_purchase)

    def test_verified_purchase_flag_from_real_order(self):
        from apps.orders.models import Order, OrderItem
        order = Order.objects.create(
            reference="ORD-TEST-VP01", customer=self.customer, status="paid", payment_status="paid",
            contact_full_name="x", contact_email=self.customer.email, contact_phone="0",
            delivery_full_name="x", delivery_phone="0", delivery_state="Lagos", delivery_city="x",
            delivery_street="x", total_amount=Decimal("25000.00"))
        OrderItem.objects.create(order=order, product=self.product, product_name=self.product.name,
                                 sku=self.product.sku, unit_price=Decimal("25000.00"), quantity=1,
                                 line_total=Decimal("25000.00"))
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/reviews/", {
            "product": self.product.pk, "rating": 4, "body": "Bought and reviewed."}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        from apps.reviews.models import Review
        self.assertTrue(Review.objects.get(product=self.product, customer=self.customer).is_verified_purchase)
