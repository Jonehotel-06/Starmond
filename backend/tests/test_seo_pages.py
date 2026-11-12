"""
Server-rendered public pages (Section 25).

Crawlers must be able to read the catalogue without executing JavaScript, and
every page must carry its own canonical URL, robots directive and structured
data. These tests assert on the returned HTML — status code, head tags, JSON-LD
payload and visible content — not on a browser.
"""
from __future__ import annotations

import json
import re

from django.test import TestCase

from apps.cms.models import ContentPage
from apps.cms.services import SettingsService
from apps.core.models import PublishableModel
from apps.seo.models import Redirect
from tests.factories import (
    make_category, make_customer, make_product, make_settings, make_shipping_zone, make_variation,
)


class PublicPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_settings()
        make_shipping_zone()
        cls.parent = make_category("Electronics")
        cls.child = make_category("Phones", parent=cls.parent)
        cls.product = make_product(
            "Galaxy A15", category=cls.child, price="185000.00", stock=10,
        )
        cls.product.description = "A dependable mid-range phone with a bright display."
        cls.product.specifications = {"Display": "6.5 inch", "Battery": "5000 mAh"}
        cls.product.key_features = ["Long battery life", "Dual SIM"]
        cls.product.save(update_fields=["description", "specifications", "key_features", "updated_at"])
        cls.draft = make_product(
            "Unreleased Phone", category=cls.child, price="1.00", stock=1, published=False,
        )
        cls.page = ContentPage.objects.create(
            slug="delivery-policy", title="Delivery policy",
            body="<p>We deliver nationwide within 2-5 working days.</p>",
            status=PublishableModel.Status.PUBLISHED,
        )

    # -- home -------------------------------------------------------------
    def test_home_page_renders_html_with_canonical_and_heading(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        html = response.content.decode()
        self.assertIn("<h1>", html)
        self.assertIn('rel="canonical"', html)
        self.assertIn("STARMOND", html)
        self.assertIn("Galaxy A15", html)

    def test_home_page_emits_organisation_structured_data(self):
        html = self.client.get("/").content.decode()
        match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        )
        self.assertIsNotNone(match)
        blocks = json.loads(match.group(1))
        types = {block.get("@type") for block in blocks}
        self.assertIn("Organization", types)
        self.assertIn("WebSite", types)

    # -- product ----------------------------------------------------------
    def test_product_page_has_price_meta_and_product_schema(self):
        response = self.client.get(self.product.absolute_path)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Galaxy A15", html)
        self.assertIn("185000.00", html)
        self.assertIn(self.product.absolute_path, html)  # canonical
        blocks = json.loads(
            re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
        )
        self.assertIn("Product", {b.get("@type") for b in blocks})

    def test_product_page_reports_stock_state_and_variation_prices(self):
        make_variation(self.product, label="128GB", price="195000.00", stock=3)
        html = self.client.get(self.product.absolute_path).content.decode()
        self.assertIn("In stock", html)
        self.assertIn("128GB", html)
        self.assertIn("195000.00", html)

    def test_draft_product_page_is_not_reachable(self):
        response = self.client.get(self.draft.absolute_path)
        self.assertEqual(response.status_code, 404)

    def test_product_page_is_permanently_redirected_to_its_canonical_url(self):
        response = self.client.get(f"/product/{self.product.slug}/")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].endswith(self.product.absolute_path))

    # -- category ---------------------------------------------------------
    def test_category_page_lists_children_and_products(self):
        response = self.client.get(self.parent.absolute_path)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Electronics", html)
        self.assertIn("Phones", html)  # sub-category link

        child_html = self.client.get(self.child.absolute_path).content.decode()
        self.assertIn("Galaxy A15", child_html)
        self.assertNotIn("Unreleased Phone", child_html)

    def test_category_page_carries_breadcrumb_structured_data(self):
        html = self.client.get(self.child.absolute_path).content.decode()
        blocks = json.loads(
            re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
        )
        self.assertIn("BreadcrumbList", {b.get("@type") for b in blocks})
        self.assertIn("Electronics", html)

    # -- shop -------------------------------------------------------------
    def test_shop_page_paginates_and_hides_drafts(self):
        for i in range(25):
            make_product(f"Bulk item {i}", category=self.child, price="1000.00", stock=1)
        first = self.client.get("/shop").content.decode()
        self.assertIn("Page 1 of 2", first)
        self.assertNotIn("Unreleased Phone", first)
        second = self.client.get("/shop?page=2").content.decode()
        self.assertIn("Page 2 of 2", second)

    def test_shop_search_filters_server_side(self):
        html = self.client.get("/shop?q=Galaxy").content.decode()
        self.assertIn("Galaxy A15", html)
        self.assertNotIn("Bulk item", html)

    def test_shop_page_number_is_validated(self):
        for bad in ("0", "-4", "abc", ""):
            response = self.client.get(f"/shop?page={bad}")
            self.assertEqual(response.status_code, 200)

    # -- content pages ----------------------------------------------------
    def test_content_page_renders_body_and_is_indexable(self):
        html = self.client.get(self.page.absolute_path).content.decode()
        self.assertIn("We deliver nationwide", html)
        self.assertIn('content="index,follow"', html)

    def test_missing_page_returns_a_real_404(self):
        response = self.client.get("/page/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertIn('content="noindex,nofollow"', response.content.decode())

    # -- redirects / 404 --------------------------------------------------
    def test_admin_managed_redirect_is_honoured(self):
        Redirect.objects.create(from_path="/old-phone", to_path=self.product.absolute_path,
                                status_code=301)
        response = self.client.get("/old-phone")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], self.product.absolute_path)

    def test_unknown_path_returns_404_not_a_soft_200(self):
        response = self.client.get("/this/does/not/exist")
        self.assertEqual(response.status_code, 404)

    def test_api_prefix_is_not_swallowed_by_the_fallback(self):
        self.assertEqual(self.client.get("/api/v1/products/").status_code, 200)

    # -- SEO surfaces stay consistent with the pages ----------------------
    def test_canonical_url_on_page_matches_the_sitemap_entry(self):
        from apps.seo.services import SEOService

        html = self.client.get(self.product.absolute_path).content.decode()
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', html).group(1)
        sitemap = SEOService.sitemap_xml()
        self.assertIn(f"<loc>{canonical}</loc>", sitemap)

    def test_private_pages_are_excluded_from_robots_indexing(self):
        self.assertIn("Disallow: /api/", SettingsService.get("business_name") and
                      self.client.get("/robots.txt").content.decode())
