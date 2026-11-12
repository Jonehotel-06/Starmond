"""
SEOService — server-rendered metadata, structured data, sitemap and robots.

The frontend must not depend on client-side JavaScript for SEO (Section 25).
These endpoints and serializer payloads give the frontend everything it needs to
emit correct ``<head>`` markup and JSON-LD on the server or at first paint.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.categories.models import Category
from apps.cms.services import SettingsService
from apps.core.models import PublishableModel
from apps.products.models import Product
from apps.seo.models import Redirect, SEOSetting

logger = logging.getLogger("apps.seo")

# Paths that must never be indexed (Section 25).
PRIVATE_PATH_PREFIXES = (
    "/api/", "/admin/", "/accounts/", "/checkout", "/cart", "/orders",
    "/payment", "/dashboard", "/refund", "/wishlist",
)


class SEOService:
    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    @staticmethod
    def default_metadata() -> dict:
        settings_map = SettingsService.all()
        title = settings_map.get("meta_title_default") or settings_map.get(
            "business_name", settings.BUSINESS_NAME
        )
        description = settings_map.get("meta_description_default") or settings_map.get(
            "business_tagline", ""
        )
        return {
            "title": title,
            "description": description,
            "keywords": "",
            "canonical": settings.SITE_URL,
            "robots": "index,follow",
            "og": {
                "title": title,
                "description": description,
                "image": "",
                "type": "website",
                "site_name": settings.BUSINESS_NAME,
                "url": settings.SITE_URL,
            },
            "twitter": {"card": "summary_large_image", "title": title, "description": description},
        }

    @classmethod
    def for_path(cls, path: str) -> dict:
        """Resolves metadata for a public URL, falling back to the default template."""
        base = cls.default_metadata()
        override = SEOSetting.objects.filter(path=path, is_active=True).first()
        if override is None:
            override = SEOSetting.objects.filter(path="*", is_active=True).first()
        if override is None:
            base["canonical"] = f"{settings.SITE_URL}{path}"
            return base

        title = override.title or base["title"]
        description = override.description or base["description"]
        return {
            "title": title,
            "description": description,
            "keywords": override.keywords,
            "canonical": override.canonical_url or f"{settings.SITE_URL}{path}",
            "robots": override.robots,
            "structured_data": override.structured_data or {},
            "og": {
                "title": override.og_title or title,
                "description": override.og_description or description,
                "image": override.og_image_url,
                "type": "website",
                "site_name": settings.BUSINESS_NAME,
                "url": f"{settings.SITE_URL}{path}",
            },
            "twitter": {
                "card": override.twitter_card,
                "title": override.og_title or title,
                "description": override.og_description or description,
            },
        }

    @staticmethod
    def product_metadata(product: Product) -> dict:
        """Complete SEO payload for a public product page."""
        title = product.meta_title or f"{product.name} — {settings.BUSINESS_NAME}"
        description = (
            product.meta_description
            or product.short_description
            or (product.description[:300] if product.description else "")
        )
        image = product.og_image_url or (
            f"{settings.SITE_URL}{product.primary_image.image.url}"
            if product.primary_image else ""
        )
        canonical = product.canonical_url or f"{settings.SITE_URL}{product.absolute_path}"
        return {
            "title": title[:200],
            "description": description[:320],
            "keywords": product.meta_keywords,
            "canonical": canonical,
            "robots": "noindex,nofollow" if product.noindex else "index,follow",
            "og": {
                "title": title[:200],
                "description": description[:320],
                "image": image,
                "type": "product",
                "site_name": settings.BUSINESS_NAME,
                "url": canonical,
                "price": str(product.price),
                "currency": product.currency,
            },
            "twitter": {"card": "summary_large_image", "title": title[:200],
                        "description": description[:320], "image": image},
            "structured_data": product.structured_data or product.build_structured_data(),
            "breadcrumbs": SEOService._product_breadcrumbs(product),
        }

    @staticmethod
    def category_metadata(category: Category) -> dict:
        title = category.meta_title or f"{category.name} — {settings.BUSINESS_NAME}"
        description = (
            category.meta_description or category.short_description
            or (category.description[:300] if category.description else "")
        )
        canonical = category.canonical_url or f"{settings.SITE_URL}{category.absolute_path}"
        image = f"{settings.SITE_URL}{category.image.url}" if category.image else ""
        return {
            "title": title[:200],
            "description": description[:320],
            "keywords": category.meta_keywords,
            "canonical": canonical,
            "robots": "index,follow" if category.status == PublishableModel.Status.PUBLISHED
            else "noindex,follow",
            "og": {
                "title": title[:200], "description": description[:320], "image": image,
                "type": "website", "site_name": settings.BUSINESS_NAME, "url": canonical,
            },
            "twitter": {"card": "summary_large_image", "title": title[:200],
                        "description": description[:320]},
            "structured_data": SEOService._category_structured_data(category),
            "breadcrumbs": category.breadcrumb(),
        }

    @staticmethod
    def _product_breadcrumbs(product: Product) -> list[dict]:
        crumbs = [{"name": "Home", "url": "/"}]
        if product.category_id:
            for node in product.category.breadcrumb():
                crumbs.append({"name": node["name"], "url": node["url"]})
        crumbs.append({"name": product.name, "url": product.absolute_path})
        return crumbs

    @staticmethod
    def _category_structured_data(category: Category) -> dict:
        return {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": category.name,
            "description": category.short_description or category.description[:300],
            "url": f"{settings.SITE_URL}{category.absolute_path}",
            "isPartOf": {"@type": "WebSite", "name": settings.BUSINESS_NAME,
                         "url": settings.SITE_URL},
        }

    @staticmethod
    def organisation_structured_data() -> dict:
        settings_map = SettingsService.all()
        data = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": settings_map.get("business_name", settings.BUSINESS_NAME),
            "url": settings.SITE_URL,
            "description": settings_map.get("business_tagline", ""),
        }
        if settings_map.get("support_email"):
            data["email"] = settings_map["support_email"]
        if settings_map.get("support_phone"):
            data["telephone"] = settings_map["support_phone"]
        socials = [
            settings_map.get(key) for key in
            ("instagram_url", "facebook_url", "twitter_url") if settings_map.get(key)
        ]
        if socials:
            data["sameAs"] = socials
        return data

    @staticmethod
    def website_structured_data() -> dict:
        """SearchAction enables the Google sitelinks search box."""
        return {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": settings.BUSINESS_NAME,
            "url": settings.SITE_URL,
            "potentialAction": {
                "@type": "SearchAction",
                "target": f"{settings.SITE_URL}/shop?q={{search_term_string}}",
                "query-input": "required name=search_term_string",
            },
        }

    @staticmethod
    def breadcrumb_structured_data(crumbs: list[dict]) -> dict:
        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index + 1,
                    "name": crumb["name"],
                    "item": f"{settings.SITE_URL}{crumb['url']}",
                }
                for index, crumb in enumerate(crumbs)
            ],
        }

    # ------------------------------------------------------------------
    # Sitemap
    # ------------------------------------------------------------------
    @classmethod
    def sitemap_entries(cls) -> list[dict]:
        """
        Every publicly indexable URL with its lastmod.

        Private pages, drafts, noindex pages and internal API endpoints are
        deliberately excluded.
        """
        from apps.cms.models import ContentPage

        entries: list[dict] = [
            {"loc": f"{settings.SITE_URL}/", "lastmod": None, "changefreq": "daily", "priority": "1.0"},
            {"loc": f"{settings.SITE_URL}/shop", "lastmod": None, "changefreq": "daily", "priority": "0.9"},
        ]

        for category in Category.objects.public().order_by("path"):
            entries.append(
                {
                    "loc": f"{settings.SITE_URL}{category.absolute_path}",
                    "lastmod": category.updated_at.date().isoformat() if category.updated_at else None,
                    "changefreq": "weekly",
                    "priority": "0.8",
                }
            )

        for product in Product.objects.public().filter(noindex=False).order_by("-updated_at"):
            entries.append(
                {
                    "loc": f"{settings.SITE_URL}{product.absolute_path}",
                    "lastmod": product.updated_at.date().isoformat() if product.updated_at else None,
                    "changefreq": "weekly",
                    "priority": "0.7",
                }
            )

        for page in ContentPage.objects.filter(status=PublishableModel.Status.PUBLISHED,
                                                noindex=False):
            entries.append(
                {
                    "loc": f"{settings.SITE_URL}{page.absolute_path}",
                    "lastmod": page.updated_at.date().isoformat() if page.updated_at else None,
                    "changefreq": "monthly",
                    "priority": "0.5",
                }
            )
        return entries

    @classmethod
    def sitemap_xml(cls) -> str:
        from xml.sax.saxutils import escape

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for entry in cls.sitemap_entries():
            lines.append("  <url>")
            lines.append(f"    <loc>{escape(entry['loc'])}</loc>")
            if entry.get("lastmod"):
                lines.append(f"    <lastmod>{entry['lastmod']}</lastmod>")
            if entry.get("changefreq"):
                lines.append(f"    <changefreq>{entry['changefreq']}</changefreq>")
            if entry.get("priority"):
                lines.append(f"    <priority>{entry['priority']}</priority>")
            lines.append("  </url>")
        lines.append("</urlset>")
        return "\n".join(lines)

    @classmethod
    def robots_txt(cls) -> str:
        lines = [
            "User-agent: *",
            "Allow: /",
        ]
        for prefix in PRIVATE_PATH_PREFIXES:
            lines.append(f"Disallow: {prefix}")
        lines += [
            "",
            f"Sitemap: {settings.SITE_URL}/sitemap.xml",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Redirects
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_redirect(path: str) -> tuple[str, int] | None:
        redirect = Redirect.objects.filter(from_path=path, is_active=True).first()
        if redirect is None:
            return None
        Redirect.objects.filter(pk=redirect.pk).update(hit_count=models_f() + 1)
        return redirect.to_path, redirect.status_code

    @staticmethod
    def is_private_path(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in PRIVATE_PATH_PREFIXES)


def models_f():
    from django.db.models import F

    return F("hit_count")
