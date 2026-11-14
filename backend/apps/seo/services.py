"""SEOService — metadata assembly, valid structured data (never fabricated),
sitemap data and cache invalidation."""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

from .models import DEFAULT_SEO_SETTINGS, SEOSetting, SitemapVersion

logger = logging.getLogger("starmond.seo")


class SEOService:
    CACHE_KEY = "seo:settings"

    # ------------------------------------------------------------ settings
    @classmethod
    def settings_values(cls):
        cached = cache.get(cls.CACHE_KEY)
        if cached:
            return cached
        row, _ = SEOSetting.objects.get_or_create(pk=True)
        merged = {**DEFAULT_SEO_SETTINGS, **(row.values or {})}
        cache.set(cls.CACHE_KEY, merged, settings.CACHE_TTL_MEDIUM)
        return merged

    @classmethod
    def update_settings(cls, patch):
        row, _ = SEOSetting.objects.get_or_create(pk=True)
        row.values = {**(row.values or {}), **patch}
        row.save(update_fields=["values", "updated_at"])
        cache.delete(cls.CACHE_KEY)
        return cls.settings_values()

    @classmethod
    def touch(cls):
        """Invalidate sitemap/prerender caches after catalogue changes."""
        row, _ = SitemapVersion.objects.get_or_create(pk=True)
        row.version += 1
        row.save(update_fields=["version", "updated_at"])
        cache.delete_pattern("seo:sitemap:*") if hasattr(cache, "delete_pattern") else cache.delete("seo:sitemap:v")
        cache.delete("cms:homepage")

    # ------------------------------------------------------------ metadata
    BRAND = "STARMOND TECHNOLOGY LIMITED"

    @classmethod
    def page_meta(cls, *, title, description, canonical=None, og_image=None, entity_type="website"):
        vals = cls.settings_values()
        template = vals.get("default_title_template", "{title}")
        if title and "{title}" in template and cls.BRAND not in title:
            final_title = template.replace("{title}", title)
        else:
            final_title = title
        return {
            "title": (final_title or vals.get("homepage_seo_title"))[:180],
            "description": (description or vals["default_meta_description"])[:320],
            "canonical_url": canonical or (vals.get("canonical_base_url") or settings.SITE_URL),
            "robots": vals.get("robots_meta_default", "index, follow"),
            "og": {
                "site_name": vals.get("default_og_site_name"),
                "title": title, "description": (description or "")[:300],
                "image": og_image, "type": entity_type,
            },
        }

    # ------------------------------------------------------- structured data
    @classmethod
    def organization_ld(cls):
        from apps.cms.services import BusinessSettingsService
        b = BusinessSettingsService.all_values()
        return {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": b.get("business_name", "STARMOND TECHNOLOGY LIMITED"),
            "url": settings.SITE_URL,
            "email": b.get("contact_email", ""),
            "telephone": b.get("contact_phone") or None,
            "address": b.get("business_address") or None,
            "sameAs": [u for u in (b.get("social_links") or {}).values() if u],
        }

    @classmethod
    def website_ld(cls):
        return {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "STARMOND TECHNOLOGY LIMITED",
            "url": settings.SITE_URL,
            "potentialAction": {
                "@type": "SearchAction",
                "target": f"{settings.SITE_URL}/search?q={{search_term_string}}",
                "query-input": "required name=search_term_string",
            },
        }

    @classmethod
    def product_ld(cls, product):
        """Product/Offer structured data built ONLY from real records.
        AggregateRating appears only when genuine approved reviews exist."""
        from apps.reviews.services import ReviewService
        image = product.main_image
        availability = "https://schema.org/InStock" if product.is_in_stock else "https://schema.org/OutOfStock"
        ld = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": product.name,
            "sku": product.sku,
            "description": (product.short_description or product.description[:300]),
            "image": [image.file_url] if image else [],
            "brand": {"@type": "Brand", "name": product.brand or "STARMOND"},
            "category": product.category.name,
            "offers": {
                "@type": "Offer",
                "url": f"{settings.SITE_URL}{product.url_path}",
                "priceCurrency": product.currency,
                "price": str(product.effective_price),
                "availability": availability,
                "seller": {"@type": "Organization", "name": "STARMOND TECHNOLOGY LIMITED"},
            },
        }
        summary = ReviewService.product_summary(product)
        if summary["review_count"] > 0 and summary["average_rating"]:
            ld["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": summary["average_rating"],
                "reviewCount": summary["review_count"],
            }
        return ld

    @classmethod
    def breadcrumb_ld(cls, items):
        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": idx + 1, "name": it["name"],
                 "item": f"{settings.SITE_URL}{it.get('url_path', '')}"}
                for idx, it in enumerate(items)
            ],
        }

    # ------------------------------------------------------------- sitemap
    @classmethod
    def sitemap_entries(cls):
        """Homepage, categories, subcategories, active products, published pages.
        Excludes admin/login/cart/checkout/private/API URLs by construction."""
        from apps.categories.models import Category
        from apps.cms.models import Page
        from apps.products.models import Product
        version, _ = SitemapVersion.objects.get_or_create(pk=True)
        cache_key = f"seo:sitemap:{version.version}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        entries = [{"loc": f"{settings.SITE_URL}/", "lastmod": None, "changefreq": "daily", "priority": "1.0"}]
        for c in Category.objects.active().only("slug", "updated_at"):
            entries.append({"loc": f"{settings.SITE_URL}{c.url_path}", "lastmod": c.updated_at,
                            "changefreq": "weekly", "priority": "0.8"})
        for p in Product.objects.public().select_related("category").only(
                "slug", "updated_at", "category__slug", "category__parent__slug"):
            entries.append({"loc": f"{settings.SITE_URL}{p.url_path}", "lastmod": p.updated_at,
                            "changefreq": "weekly", "priority": "0.7"})
        for pg in Page.objects.filter(is_published=True).only("slug", "updated_at"):
            entries.append({"loc": f"{settings.SITE_URL}/page/{pg.slug}/", "lastmod": pg.updated_at,
                            "changefreq": "monthly", "priority": "0.5"})
        cache.set(cache_key, entries, settings.CACHE_TTL_LONG)
        return entries
