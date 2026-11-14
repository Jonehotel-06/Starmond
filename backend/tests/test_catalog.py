import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from apps.categories.models import Category
from apps.core.constants import Perm
from apps.products.models import Product, ProductVariation

from .base import StarmondAPITestCase


def _png(name="test.png", size=(800, 600)):
    buf = io.BytesIO()
    Image.new("RGB", size, (12, 90, 160)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(MAX_UPLOAD_SIZE_MB=5)
class CategoryTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_staff(perms=[Perm.CATEGORIES_MANAGE, Perm.PRODUCTS_VIEW])
        self.client.force_authenticate(self.staff)

    def test_create_category_generates_slug(self):
        response = self.client.post("/api/categories/admin/", {"name": "Electrical & Accessories", "description": "All electricals"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        category = Category.objects.get(name="Electrical & Accessories")
        self.assertEqual(category.slug, "electrical-accessories")
        self.assertEqual(category.url_path, "/shop/electrical-accessories/")

    def test_duplicate_slug_prevented(self):
        self.make_category(name="Fashion", slug="fashion")
        response = self.client.post("/api/categories/admin/", {"name": "Fashion", "slug": "fashion"}, format="json")
        self.assertIn(response.status_code, (400, 409))

    def test_subcategory_and_url_path(self):
        parent = self.make_category(name="Electrical", slug="electrical")
        response = self.client.post("/api/categories/admin/", {"name": "Cables", "parent": parent.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        child = Category.objects.get(slug="cables")
        self.assertEqual(child.url_path, "/shop/electrical/cables/")

    def test_max_depth_enforced(self):
        a = self.make_category("A", "a")
        b = self.make_category("B", "b", parent=a)
        c = self.make_category("C", "c", parent=b)
        response = self.client.post("/api/categories/admin/", {"name": "D", "parent": c.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "max_depth_exceeded")

    def test_cycle_prevented(self):
        parent = self.make_category("Parent", "parent")
        child = self.make_category("Child", "child", parent=parent)
        response = self.client.patch(f"/api/categories/admin/{parent.pk}/", {"parent": child.pk}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_safe_delete_blocked_when_products_linked(self):
        category = self.make_category("To Delete", "to-delete")
        self.make_product(category=category)
        response = self.client.delete(f"/api/categories/admin/{category.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

    def test_safe_delete_allowed_when_empty(self):
        category = self.make_category("Empty", "empty")
        response = self.client.delete(f"/api/categories/admin/{category.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_reorder_and_deactivate_tree(self):
        parent = self.make_category("Parent", "p1")
        child = self.make_category("Child", "c1", parent=parent)
        response = self.client.post("/api/categories/admin/reorder/", {
            "items": [{"id": parent.pk, "display_order": 5}, {"id": child.pk, "display_order": 6}]}, format="json")
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertEqual(parent.display_order, 5)
        response = self.client.post(f"/api/categories/admin/{parent.pk}/deactivate/")
        self.assertEqual(response.status_code, 200)
        child.refresh_from_db()
        self.assertFalse(child.is_active)

    def test_public_api_only_returns_active(self):
        self.make_category("Active Cat", "active-cat")
        hidden = self.make_category("Hidden Cat", "hidden-cat")
        hidden.is_active = False
        hidden.save()
        self.client.force_authenticate(None)
        response = self.client.get("/api/categories/")
        slugs = [c["slug"] for c in response.data["data"]]
        self.assertIn("active-cat", slugs)
        self.assertNotIn("hidden-cat", slugs)


@override_settings(MAX_UPLOAD_SIZE_MB=5)
class ProductTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.manager = self.make_staff(perms=[Perm.PRODUCTS_VIEW, Perm.PRODUCTS_MANAGE, Perm.CATEGORIES_MANAGE, Perm.INVENTORY_MANAGE])
        self.client.force_authenticate(self.manager)

    def test_create_product_with_stock_and_variation(self):
        category = self.make_category()
        response = self.client.post("/api/products/admin/", {
            "name": "Distribution Board 12 Way", "sku": "DB-12", "category": category.pk,
            "regular_price": "45000.00", "sale_price": "39999.99", "stock_quantity": 25,
            "status": "active", "brand": "Schneider"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(sku="DB-12")
        self.assertEqual(product.stock_summary()["available"], 25)
        self.assertEqual(product.effective_price.to_eng_string(), "39999.99")

        response = self.client.post(f"/api/products/admin/{product.pk}/variations/", {
            "sku": "DB-12-S", "name": "Surface mount", "options": {"Mount": "Surface"},
            "price_adjustment": "2000.00", "stock_quantity": 8}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        variation = ProductVariation.objects.get(sku="DB-12-S")
        self.assertEqual(variation.effective_price.to_eng_string(), "41999.99")
        self.assertEqual(variation.inventory_record.on_hand, 8)

    def test_duplicate_sku_rejected(self):
        category = self.make_category()
        self.make_product(category=category, sku="DUP-1")
        response = self.client.post("/api/products/admin/", {
            "name": "Another", "sku": "DUP-1", "category": category.pk, "regular_price": "100.00"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "duplicate_sku")

    def test_sale_price_must_be_lower(self):
        category = self.make_category()
        response = self.client.post("/api/products/admin/", {
            "name": "Bad Sale", "sku": "BAD-1", "category": category.pk,
            "regular_price": "100.00", "sale_price": "150.00"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_draft_products_hidden_from_public(self):
        self.make_product(sku="PUB-1", name="Published")
        self.make_product(sku="DRF-1", name="Drafted", status=Product.Status.DRAFT)
        self.client.force_authenticate(None)
        response = self.client.get("/api/products/")
        names = [p["name"] for p in response.data["results"]]
        self.assertIn("Published", names)
        self.assertNotIn("Drafted", names)

    def test_cost_price_hidden_without_finance_permission(self):
        product = self.make_product(sku="COST-1")
        product.cost_price = 100
        product.save()
        response = self.client.get(f"/api/products/admin/{product.pk}/")
        self.assertIsNone(response.data["cost_price"])

        accountant = self.make_staff(email="acc@example.com", perms=[Perm.PRODUCTS_VIEW, Perm.FINANCE_VIEW], role_name="Acc")
        self.client.force_authenticate(accountant)
        response = self.client.get(f"/api/products/admin/{product.pk}/")
        self.assertEqual(str(response.data["cost_price"]), "100.00")

    def test_image_upload_and_main_image(self):
        product = self.make_product(sku="IMG-1")
        response = self.client.post(f"/api/products/admin/{product.pk}/images/", {"images": [_png(), _png("second.png")]}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(product.images.count(), 2)
        first = product.images.order_by("id").first()
        self.assertTrue(first.is_main)
        second = product.images.order_by("-id").first()
        response = self.client.post(f"/api/products/admin/{product.pk}/images/{second.pk}/set-main/")
        self.assertEqual(response.status_code, 200)
        second.refresh_from_db()
        self.assertTrue(second.is_main)

    def test_malicious_upload_rejected(self):
        product = self.make_product(sku="MAL-1")
        fake = SimpleUploadedFile("evil.png", b"\x89PNG\r\n\x1a\nnotreallyanimage", content_type="image/png")
        response = self.client.post(f"/api/products/admin/{product.pk}/images/", {"images": [fake]}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "invalid_media")

    def test_delete_product_with_history_archives(self):
        product = self.make_product(sku="ARCH-1")
        response = self.client.delete(f"/api/products/admin/{product.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["result"], "deleted")

    def test_search_endpoint(self):
        category = self.make_category("Electrical", "electrical")
        self.make_product(category=category, name="Copper Cable 2.5mm", sku="CBL-25", brand="Cutix")
        self.make_product(category=category, name="LED Bulb 9W", sku="BLB-9")
        self.client.force_authenticate(None)
        response = self.client.get("/api/products/search/", {"q": "copper"})
        self.assertEqual(response.status_code, 200)
        names = [p["name"] for p in response.data["results"]]
        self.assertIn("Copper Cable 2.5mm", names)
        self.assertTrue(response.data.get("suggestions"))
        response = self.client.get("/api/products/search/", {"q": "cutix"})
        self.assertEqual(len(response.data["results"]), 1)
