from apps.core.constants import Perm
from apps.cms.models import Page
from apps.seo.services import SEOService

from .base import StarmondAPITestCase


class SEOTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.category = self.make_category("Electrical", "electrical")
        self.sub = self.make_category("Cables", "cables", parent=self.category)
        self.product = self.make_product(category=self.sub, name="Copper Cable 2.5mm", sku="CBL-25", price="15000.00")
        Page.objects.create(title="Privacy Policy", slug="privacy-policy", body="<p>We respect privacy.</p>",
                            excerpt="How we handle data", is_published=True)
        Page.objects.create(title="Internal Draft", slug="draft-page", is_published=False)

    def test_robots_txt(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Disallow: /api/", content)
        self.assertIn("Disallow: /django-admin/", content)
        self.assertIn("Sitemap:", content)
        self.assertIn("Allow: /", content)

    def test_sitemap_includes_public_urls_and_excludes_private(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("/shop/electrical/", content)
        self.assertIn("/shop/electrical/cables/", content)
        self.assertIn("cbl-25", content)
        self.assertIn("/page/privacy-policy/", content)
        self.assertNotIn("draft-page", content)
        self.assertNotIn("/api/", content)
        self.assertNotIn("django-admin", content)
        self.assertIn("<lastmod>", content)

    def test_product_structured_data(self):
        response = self.client.get(f"/api/seo/structured-data/product/{self.product.slug}/")
        self.assertEqual(response.status_code, 200, response.data)
        ld = response.data["data"][0]
        self.assertEqual(ld["@type"], "Product")
        self.assertEqual(ld["sku"], "CBL-25")
        self.assertEqual(ld["offers"]["price"], "15000.00")
        self.assertEqual(ld["offers"]["priceCurrency"], "NGN")
        self.assertEqual(ld["offers"]["availability"], "https://schema.org/InStock")
        # AggregateRating must NOT be fabricated when there are no reviews
        self.assertNotIn("aggregateRating", ld)
        breadcrumb = response.data["data"][1]
        self.assertEqual(breadcrumb["@type"], "BreadcrumbList")

    def test_aggregate_rating_only_with_real_reviews(self):
        from apps.reviews.models import Review
        Review.objects.create(product=self.product, rating=4, body="ok", moderation_status="approved")
        Review.objects.create(product=self.product, rating=5, body="great", moderation_status="pending")
        response = self.client.get(f"/api/seo/structured-data/product/{self.product.slug}/")
        ld = response.data["data"][0]
        self.assertIn("aggregateRating", ld)
        self.assertEqual(ld["aggregateRating"]["reviewCount"], 1)  # only approved
        self.assertEqual(ld["aggregateRating"]["ratingValue"], 4.0)

    def test_organization_and_website_ld(self):
        response = self.client.get("/api/seo/structured-data/organization/")
        self.assertEqual(response.data["data"]["@type"], "Organization")
        self.assertEqual(response.data["data"]["name"], "STARMOND TECHNOLOGY LIMITED")
        response = self.client.get("/api/seo/structured-data/website/")
        self.assertIn("potentialAction", response.data["data"])

    def test_prerendered_product_page_crawlable(self):
        response = self.client.get(self.product.url_path)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("<title>", html)
        self.assertIn("Copper Cable 2.5mm", html)
        self.assertIn("application/ld+json", html)
        self.assertIn("15000", html)
        self.assertIn("In stock", html)
        self.assertIn('rel="canonical"', html)

    def test_prerendered_category_page(self):
        response = self.client.get("/shop/electrical/cables/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Cables", html)
        self.assertIn("Copper Cable 2.5mm", html)

    def test_prerender_404_for_unknown(self):
        response = self.client.get("/shop/nope/missing/")
        self.assertEqual(response.status_code, 404)

    def test_seo_settings_staff_api(self):
        staff = self.make_staff(perms=[Perm.SEO_MANAGE], role_name="SEO")
        self.client.force_authenticate(staff)
        response = self.client.get("/api/seo/settings/")
        self.assertEqual(response.status_code, 200)
        response = self.client.patch("/api/seo/settings/", {"homepage_seo_title": "Custom Title"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SEOService.settings_values()["homepage_seo_title"], "Custom Title")

    def test_product_seo_update_and_preview(self):
        staff = self.make_staff(perms=[Perm.SEO_MANAGE], role_name="SEO2")
        self.client.force_authenticate(staff)
        response = self.client.patch(f"/api/seo/products/{self.product.slug}/", {
            "seo_title": "Buy Copper Cable 2.5mm in Nigeria", "seo_description": "Genuine copper cable."}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post("/api/seo/preview-snippet/", {
            "title": "x" * 90, "description": "y" * 200, "url": "/shop/a/"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["warnings"])

    def test_public_settings_endpoint(self):
        response = self.client.get("/api/cms/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["business_name"], "STARMOND TECHNOLOGY LIMITED")

    def test_public_pages_api(self):
        response = self.client.get("/api/cms/pages/")
        slugs = [p["slug"] for p in response.data["data"]]
        self.assertIn("privacy-policy", slugs)
        self.assertNotIn("draft-page", slugs)
