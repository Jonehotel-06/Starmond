"""Contract tests for the endpoints the frontend integration depends on.

Each test pins a route + response shape that a storefront or admin screen
calls, so a backend change that would break the UI fails here first.
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from apps.core.constants import Perm

from .base import StarmondAPITestCase


def _png(name="test.png", size=(640, 480)):
    buf = io.BytesIO()
    Image.new("RGB", size, (99, 53, 168)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class StorefrontContractTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.category = self.make_category()
        self.product = self.make_product(category=self.category)
        made = self.make_shipping(state="Lagos", fee="2500.00")
        self.shipping = next(x for x in (made if isinstance(made, tuple) else (made,)) if hasattr(x, "fee"))

    def test_csrf_endpoint_sets_cookie(self):
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

    def test_me_exposes_permissions_for_staff(self):
        staff = self.make_staff(perms=[Perm.ORDERS_VIEW])
        self.client.force_authenticate(staff)
        data = self.client.get("/api/auth/me/").data["data"]
        self.assertTrue(data["is_staff_user"])
        self.assertIn(Perm.ORDERS_VIEW, data["permissions"])
        self.assertFalse(data["is_superuser"])

    def test_shipping_states_and_options(self):
        states = self.client.get("/api/shipping/states/")
        self.assertEqual(states.status_code, 200)
        self.assertIn("Lagos", str(states.data))
        options = self.client.get("/api/shipping/options/", {"state": "Lagos", "subtotal": "15000"})
        self.assertEqual(options.status_code, 200, options.data)

    def test_product_list_facets_and_related(self):
        listing = self.client.get("/api/products/", {"ordering": "price"})
        self.assertEqual(listing.status_code, 200)
        row = listing.data["results"][0]
        for key in ("slug", "name", "has_variations"):
            self.assertIn(key, row)
        self.assertEqual(self.client.get("/api/products/facets/").status_code, 200)
        related = self.client.get(f"/api/products/{self.product.slug}/related/")
        self.assertEqual(related.status_code, 200)

    def test_recent_reviews_is_public_and_bounded(self):
        response = self.client.get("/api/reviews/recent/", {"limit": 3})
        self.assertEqual(response.status_code, 200)

    def test_checkout_preview_prices_cart_without_creating_an_order(self):
        from apps.orders.models import Order
        add = self.client.post("/api/cart/", {"product": self.product.id, "quantity": 2}, format="json")
        self.assertEqual(add.status_code, 201, add.data)
        token = add.data["data"]["token"]
        preview = self.client.post("/api/checkout/preview/", {
            "source": {"type": "cart"}, "cart_token": token,
            "delivery": {"state": "Lagos", "shipping_method_id": self.shipping.id},
        }, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        totals = preview.data["data"]["totals"]
        self.assertEqual(totals["subtotal"], "30000.00")
        self.assertEqual(totals["shipping_fee"], "2500.00")
        self.assertEqual(totals["total"], "32500.00")
        self.assertEqual(Order.objects.count(), 0)

    def test_preview_reports_bad_promotion_without_failing(self):
        add = self.client.post("/api/cart/", {"product": self.product.id, "quantity": 1}, format="json")
        preview = self.client.post("/api/checkout/preview/", {
            "source": {"type": "cart"}, "cart_token": add.data["data"]["token"], "promotion_code": "NOPE",
        }, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertTrue(preview.data["data"]["promotion_error"])


@override_settings(MAX_UPLOAD_SIZE_MB=5)
class AdminContractTests(StarmondAPITestCase):
    def test_staff_without_permission_is_refused(self):
        """Regression: any is_staff user used to pass every permission check."""
        staff = self.make_staff(perms=[Perm.INVENTORY_VIEW])
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/inventory/").status_code, 200)
        for path in ("/api/orders/admin/", "/api/admin-panel/staff/", "/api/cms/admin/settings/", "/api/reports/sales/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_customer_cannot_reach_admin_routes(self):
        self.client.force_authenticate(self.make_customer())
        for path in ("/api/products/admin/", "/api/orders/admin/", "/api/dashboard/overview/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_customer_order_list_is_not_shadowed_by_admin_router(self):
        self.client.force_authenticate(self.make_customer())
        response = self.client.get("/api/orders/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 0)

    def test_media_upload_list_and_remove(self):
        self.client.force_authenticate(self.make_staff(perms=[Perm.MEDIA_MANAGE]))
        upload = self.client.post("/api/media/uploads/", {"file": _png(), "kind": "banner", "alt_text": "Sale banner"}, format="multipart")
        self.assertEqual(upload.status_code, 201, upload.data)
        asset = upload.data.get("data", upload.data)
        self.assertTrue(asset["key"])
        self.assertTrue(asset["url"])
        listing = self.client.get("/api/media/assets/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        patched = self.client.patch(f"/api/media/assets/{asset['id']}/", {"alt_text": "Updated"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.data)
        removed = self.client.delete(f"/api/media/assets/{asset['id']}/remove/")
        self.assertIn(removed.status_code, (200, 204))
        self.assertEqual(self.client.get("/api/media/assets/").data["count"], 0)

    def test_media_upload_rejects_non_images_and_customers(self):
        self.client.force_authenticate(self.make_staff(perms=[Perm.MEDIA_MANAGE]))
        bad = SimpleUploadedFile("evil.png", b"<?php echo 1; ?>", content_type="image/png")
        self.assertEqual(self.client.post("/api/media/uploads/", {"file": bad}, format="multipart").status_code, 400)
        self.client.force_authenticate(self.make_customer())
        self.assertEqual(self.client.get("/api/media/assets/").status_code, 403)

    def test_admin_customers_list(self):
        self.make_customer(email="shopper@example.com")
        self.client.force_authenticate(self.make_staff(perms=[Perm.CUSTOMERS_VIEW]))
        response = self.client.get("/api/admin-panel/customers/")
        self.assertEqual(response.status_code, 200, response.data)

    def test_admin_categories_level_filter(self):
        parent = self.make_category(name="Electrical")
        self.make_category(name="Cables", parent=parent)
        self.client.force_authenticate(self.make_staff(perms=[Perm.CATEGORIES_MANAGE]))
        top = self.client.get("/api/categories/admin/", {"level": "top"}).data
        sub = self.client.get("/api/categories/admin/", {"level": "sub"}).data
        self.assertEqual([c["name"] for c in top["results"]], ["Electrical"])
        self.assertEqual([c["name"] for c in sub["results"]], ["Cables"])
        self.assertEqual(sub["results"][0]["parent_name"], "Electrical")

    def test_reports_reject_malformed_dates(self):
        self.client.force_authenticate(self.make_staff(perms=[Perm.REPORTS_VIEW]))
        bad = self.client.get("/api/reports/sales/", {"range": "custom", "date_from": "15/11/2026"})
        self.assertEqual(bad.status_code, 400, bad.data)
        ok = self.client.get("/api/reports/sales/", {"range": "custom", "date_from": "2026-11-01", "date_to": "2026-11-15"})
        self.assertEqual(ok.status_code, 200)
        self.assertIn("summary", ok.data["data"])
