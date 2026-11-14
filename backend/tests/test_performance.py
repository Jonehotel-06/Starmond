"""Performance measurement tests.

These tests seed a realistic catalogue (200 products across nested categories)
and MEASURE actual response times and query counts. Findings are printed so
they can be recorded honestly in the performance report. Bounds are enforced
to catch N+1 regressions.
"""
import time

from django.db import connection
from django.test.utils import CaptureQueriesContext

from .base import StarmondAPITestCase


class PerformanceTests(StarmondAPITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from decimal import Decimal
        from apps.categories.models import Category
        from apps.products.models import Product
        from apps.inventory.services import InventoryService
        cls.root_cats = []
        for i, name in enumerate(["Electrical", "Fashion", "Electronics", "Accessories", "Home"]):
            root = Category.objects.create(name=name, slug=name.lower(), display_order=i)
            for j in range(3):
                sub = Category.objects.create(name=f"{name} Sub {j}", slug=f"{name.lower()}-sub-{j}", parent=root)
                cls.root_cats.append(sub)
        cls.products = []
        for i in range(200):
            category = cls.root_cats[i % len(cls.root_cats)]
            product = Product.objects.create(
                name=f"Product {i}", sku=f"PERF-{i:04d}", slug=f"product-{i}",
                category=category, regular_price=Decimal(1000 + i * 10),
                sale_price=Decimal(900 + i * 10) if i % 3 == 0 else None,
                short_description=f"Short description for product {i}",
                description="Long description. " * 20,
                status="active", is_featured=(i % 10 == 0), is_new_arrival=(i % 7 == 0),
                brand=f"Brand {i % 9}", tags=f"tag{i % 5},common")
            cls.products.append(product)
        for product in Product.objects.all():
            InventoryService.ensure_inventory(product, None, opening=25)

    def assertMaxQueries(self, max_n, func, *args, **kwargs):
        with CaptureQueriesContext(connection) as ctx:
            result = func(*args, **kwargs)
        self.assertLessEqual(len(ctx), max_n, f"Executed {len(ctx)} queries (limit {max_n})")
        return result

    def _timed(self, url, params=None, runs=20):
        start = time.perf_counter()
        for _ in range(runs):
            response = self.client.get(url, params or {})
            self.assertEqual(response.status_code, 200)
        elapsed = (time.perf_counter() - start) / runs * 1000
        return elapsed, response

    def test_product_list_query_count_and_time(self):
        avg, response = self._timed("/api/products/", {"page_size": 20})
        self.assertMaxQueries(8, self.client.get, "/api/products/", {"page_size": 20})
        print(f"\n[PERF] product list (20 items, 200 in DB): {avg:.1f} ms avg")
        self.assertLess(avg, 500)

    def test_product_detail_query_count_and_time(self):
        product = self.products[0]
        avg, _ = self._timed(f"/api/products/{product.slug}/", runs=20)
        self.assertMaxQueries(14, self.client.get, f"/api/products/{product.slug}/")
        print(f"[PERF] product detail: {avg:.1f} ms avg")
        self.assertLess(avg, 500)

    def test_search_time(self):
        avg, response = self._timed("/api/products/search/", {"q": "product 1"}, runs=10)
        print(f"[PERF] search 'product 1' (of 200): {avg:.1f} ms avg, {response.data['count']} hits")
        self.assertLess(avg, 800)

    def test_homepage_payload_is_small(self):
        avg, response = self._timed("/api/cms/homepage/", runs=10)
        payload = response.data["data"]
        self.assertLessEqual(len(payload["featured"]), 8)
        self.assertLessEqual(len(payload["new_arrivals"]), 8)
        print(f"[PERF] homepage payload: {avg:.1f} ms avg, featured={len(payload['featured'])}")
        self.assertLess(avg, 600)

    def test_category_tree_time(self):
        avg, response = self._timed("/api/categories/", runs=10)
        print(f"[PERF] category tree: {avg:.1f} ms avg")
        self.assertLess(avg, 600)

    def test_cart_operations_time(self):
        product = self.products[5]
        start = time.perf_counter()
        for _ in range(10):
            response = self.client.post("/api/cart/", {"product": product.pk, "quantity": 1}, format="json")
            self.assertEqual(response.status_code, 201)
        elapsed = (time.perf_counter() - start) / 10 * 1000
        print(f"[PERF] cart add: {elapsed:.1f} ms avg")
        self.assertLess(elapsed, 500)
