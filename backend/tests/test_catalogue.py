"""Catalogue management, variations, publication rules and search."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.categories.models import Category
from apps.categories.services import CategoryService
from apps.core.exceptions import ConflictError, ValidationError
from apps.core.models import PublishableModel
from apps.inventory.models import Inventory
from apps.products.models import Product, ProductAttribute, ProductAttributeValue
from apps.products.services import ProductService
from tests.factories import make_category, make_product, make_settings, make_staff


class CategoryTests(TestCase):
    def setUp(self):
        make_settings()
        self.staff = make_staff()

    def test_unlimited_nesting(self):
        parent = None
        for depth in range(6):
            parent = CategoryService.create(name=f"Level {depth}", parent=parent)
        self.assertEqual(parent.depth, 5)
        self.assertIn("level-0/level-1/level-2", parent.path)

    def test_slug_is_unique(self):
        first = CategoryService.create(name="Phones")
        second = CategoryService.create(name="Phones", parent=first)
        self.assertNotEqual(first.slug, second.slug)

    def test_sibling_names_must_be_unique(self):
        parent = CategoryService.create(name="Electronics")
        CategoryService.create(name="Phones", parent=parent)
        with self.assertRaises(ConflictError):
            CategoryService.create(name="Phones", parent=parent)

    def test_same_name_allowed_under_different_parents(self):
        a = CategoryService.create(name="Laptops")
        b = CategoryService.create(name="Phones")
        CategoryService.create(name="Accessories", parent=a)
        CategoryService.create(name="Accessories", parent=b)  # must not raise

    def test_cannot_delete_category_with_products(self):
        category = make_category()
        make_product(category=category)
        with self.assertRaises(ConflictError):
            CategoryService.delete(category)

    def test_cannot_delete_category_with_children(self):
        parent = CategoryService.create(name="Parent")
        CategoryService.create(name="Child", parent=parent)
        with self.assertRaises(ConflictError):
            CategoryService.delete(parent)

    def test_descendants_are_included_when_browsing_a_parent(self):
        parent = CategoryService.create(name="Fashion")
        child = CategoryService.create(name="Shoes", parent=parent)
        product = make_product(category=child)
        self.assertIn(product.pk, Product.objects.in_category_tree(parent).values_list("pk", flat=True))

    def test_tree_endpoint_returns_nested_structure(self):
        parent = CategoryService.create(name="Home", status="published")
        CategoryService.create(name="Kitchen", parent=parent, status="published")
        tree = CategoryService.tree()
        names = [node["name"] for node in tree]
        self.assertIn("Home", names)

    def test_public_category_lookup_hides_drafts(self):
        draft = make_category(published=False)
        from apps.core.exceptions import NotFound

        with self.assertRaises(NotFound):
            CategoryService.get_public(draft.slug)


class ProductTests(TestCase):
    def setUp(self):
        make_settings()
        self.staff = make_staff()
        self.category = make_category()

    def test_create_product_sets_slug_and_sku(self):
        product = ProductService.create_product(
            name="Wireless Earbuds", category=self.category, price="25000.00",
            sku="stm-earbud-1", actor=self.staff, opening_stock=12,
        )
        self.assertEqual(product.sku, "STM-EARBUD-1")
        self.assertEqual(product.slug, "wireless-earbuds")
        inventory = Inventory.objects.get(product=product, variation=None)
        self.assertEqual(inventory.quantity_on_hand, 12)

    def test_duplicate_sku_is_rejected(self):
        ProductService.create_product(
            name="Item A", category=self.category, price="100", sku="DUP-1", opening_stock=1
        )
        with self.assertRaises(ConflictError):
            ProductService.create_product(
                name="Item B", category=self.category, price="100", sku="DUP-1", opening_stock=1
            )

    def test_cannot_add_product_to_unpublished_category(self):
        draft = make_category(published=False)
        with self.assertRaises(ValidationError):
            ProductService.create_product(
                name="Hidden", category=draft, price="100", sku="HID-1"
            )

    def test_negative_price_is_rejected(self):
        with self.assertRaises(ValidationError):
            ProductService.create_product(
                name="Bad", category=self.category, price="-5", sku="BAD-1"
            )

    def test_compare_at_price_must_not_be_lower_than_price(self):
        with self.assertRaises(Exception):
            ProductService.create_product(
                name="Sale", category=self.category, price="5000", sku="SALE-1",
                compare_at_price="4000",
            )

    def test_price_change_is_audited(self):
        product = make_product(price="1000.00")
        ProductService.update_product(product, price="1500.00", actor=self.staff)
        from apps.audit.models import AuditLog

        self.assertTrue(
            AuditLog.objects.filter(action="price_changed", entity_id=str(product.pk)).exists()
        )

    def test_publishing_creates_inventory_record(self):
        product = make_product(published=False)
        Inventory.objects.filter(product=product).delete()
        published = ProductService.publish(product, actor=self.staff)
        self.assertEqual(published.status, PublishableModel.Status.PUBLISHED)
        self.assertTrue(Inventory.objects.filter(product=product).exists())

    def test_cannot_publish_product_in_draft_category(self):
        draft = make_category(published=False)
        product = Product.objects.create(
            name="Draft cat product", slug="draft-cat-product", sku="DCP-1",
            category=draft, price=Decimal("100"),
        )
        with self.assertRaises(ConflictError):
            ProductService.publish(product, actor=self.staff)

    def test_deleting_a_sold_product_archives_instead(self):
        from tests.test_orders import paid_order
        from tests.factories import make_customer, make_shipping_zone

        make_shipping_zone()
        product = make_product(price="1000.00", stock=5)
        paid_order(make_customer(), product, key="catalogue-archive-1")
        ProductService.delete_product(product, actor=self.staff)
        product.refresh_from_db()
        self.assertEqual(product.status, PublishableModel.Status.ARCHIVED)

    def test_deleting_an_unsold_product_is_soft(self):
        product = make_product()
        ProductService.delete_product(product, actor=self.staff)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        self.assertTrue(Product.all_objects.filter(pk=product.pk).exists())


class VariationTests(TestCase):
    def setUp(self):
        make_settings()
        self.staff = make_staff()
        self.product = make_product(price="10000.00", stock=0)
        attribute = ProductAttribute.objects.create(
            name="Colour", slug="colour", is_variation_axis=True
        )
        self.red = ProductAttributeValue.objects.create(
            attribute=attribute, value="Red", slug="red"
        )
        self.blue = ProductAttributeValue.objects.create(
            attribute=attribute, value="Blue", slug="blue"
        )

    def test_variation_has_its_own_price_and_stock(self):
        red = ProductService.add_variation(
            product=self.product, sku="VAR-RED", attribute_value_ids=[str(self.red.pk)],
            price_override="12000.00", opening_stock=4, actor=self.staff,
        )
        blue = ProductService.add_variation(
            product=self.product, sku="VAR-BLUE", attribute_value_ids=[str(self.blue.pk)],
            price_override="15000.00", opening_stock=2, actor=self.staff,
        )
        self.assertEqual(red.effective_price, Decimal("12000.00"))
        self.assertEqual(blue.effective_price, Decimal("15000.00"))
        self.assertNotEqual(red.effective_price, blue.effective_price)

        product = Product.objects.get(pk=self.product.pk)
        self.assertTrue(product.is_variation_based)

    def test_variation_inherits_product_price_when_no_override(self):
        variation = ProductService.add_variation(
            product=self.product, sku="VAR-INHERIT",
            attribute_value_ids=[str(self.blue.pk)], opening_stock=1, actor=self.staff,
        )
        self.assertEqual(variation.effective_price, Decimal("10000.00"))

    def test_duplicate_variation_sku_is_rejected(self):
        ProductService.add_variation(
            product=self.product, sku="VAR-DUP", attribute_value_ids=[str(self.red.pk)],
            opening_stock=1, actor=self.staff,
        )
        with self.assertRaises(ConflictError):
            ProductService.add_variation(
                product=self.product, sku="VAR-DUP", attribute_value_ids=[str(self.blue.pk)],
                opening_stock=1, actor=self.staff,
            )

    def test_variation_requires_at_least_one_attribute(self):
        with self.assertRaises(ValidationError):
            ProductService.add_variation(
                product=self.product, sku="VAR-NONE", attribute_value_ids=[],
                opening_stock=1, actor=self.staff,
            )


class SearchTests(TestCase):
    def setUp(self):
        make_settings()
        self.phones = CategoryService.create(name="Phones", status="published")
        self.audio = CategoryService.create(name="Audio", status="published")
        self.iphone = make_product(name="iPhone 15 Pro", category=self.phones, price="1500000.00")
        self.earbuds = make_product(name="Wireless Earbuds", category=self.audio, price="25000.00")
        self.draft = make_product(name="iPhone 16 Secret", category=self.phones, published=False)

    def test_search_matches_name(self):
        results = ProductService.search(query="iPhone")
        self.assertIn(self.iphone, results)
        self.assertNotIn(self.draft, results)

    def test_search_is_category_aware(self):
        results = ProductService.search(query="", category=self.audio)
        self.assertIn(self.earbuds, results)
        self.assertNotIn(self.iphone, results)

    def test_search_excludes_unpublished_products(self):
        results = ProductService.search(query="Secret")
        self.assertNotIn(self.draft, results)

    def test_price_filters(self):
        results = ProductService.search(query="", max_price="50000")
        self.assertIn(self.earbuds, results)
        self.assertNotIn(self.iphone, results)

    def test_sorting_by_price(self):
        results = list(ProductService.search(query="", sort="price_low"))
        self.assertEqual(results[0], self.earbuds)

    def test_search_endpoint_is_paginated(self):
        response = self.client.get("/api/v1/products/search/?q=iPhone")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("results", body)
        self.assertIn("count", body)
        self.assertLessEqual(len(body["results"]), 100)

    def test_product_detail_endpoint_exposes_seo_and_variations(self):
        response = self.client.get(f"/api/v1/products/{self.iphone.slug}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("seo", data)
        self.assertIn("structured_data", data["seo"])
        self.assertEqual(data["seo"]["robots"], "index,follow")

    def test_cost_price_never_leaks_to_the_public_api(self):
        self.iphone.cost_price = Decimal("900000.00")
        self.iphone.save(update_fields=["cost_price"])
        response = self.client.get(f"/api/v1/products/{self.iphone.slug}/")
        self.assertNotIn("cost_price", str(response.json()))
