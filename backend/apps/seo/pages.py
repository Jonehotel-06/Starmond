"""
Server-rendered public pages.

Section 25 requires the public catalogue to be crawlable **without executing
JavaScript**: real HTML for the home page, the shop listing, category pages,
product pages and CMS content pages, each carrying its own ``<title>``,
meta description, canonical link, robots directive, Open Graph tags and
JSON-LD structured data.

These views are deliberately framework-free — plain Django templates, inline
CSS, no build step and no frontend framework — so the storefront is complete
and indexable even before any client application is attached.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.db.models import Count, Q
from django.http import Http404, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import render
from django.views import View

from apps.categories.models import Category
from apps.cms.models import ContentPage
from apps.cms.services import SettingsService
from apps.core.models import PublishableModel
from apps.inventory.services import InventoryService
from apps.products.models import Product
from apps.seo.services import SEOService

PAGE_SIZE = 20


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _json_ld(*blocks: dict) -> str:
    """Serialise one or more structured-data blocks for inline embedding."""
    return json.dumps([b for b in blocks if b], ensure_ascii=False, indent=None)


def _site_context(**extra) -> dict:
    """Context every page needs: business identity, navigation and footer."""
    ctx = {
        "business_name": settings.BUSINESS_NAME,
        "site_url": settings.SITE_URL,
        "currency": settings.DEFAULT_CURRENCY,
        "support_email": SettingsService.get("support_email", ""),
        "support_phone": SettingsService.get("support_phone", ""),
        "whatsapp_number": SettingsService.get("whatsapp_number", ""),
        "business_address": SettingsService.get("business_address", ""),
        "tagline": SettingsService.get("business_tagline", ""),
        "nav_categories": list(
            Category.objects.public()
            .filter(parent__isnull=True)
            .order_by("position", "name")[:12]
        ),
        "footer_pages": ContentPage.objects.filter(
            status=PublishableModel.Status.PUBLISHED,
            noindex=False,
            show_in_footer=True,
        ).order_by("position", "title")[:8],
    }
    ctx.update(extra)
    return ctx


def _render(request, template: str, context: dict, *, status: int = 200):
    return render(request, template, _site_context(**context), status=status)


def _page_meta(title, description, canonical, *, robots="index,follow", image="", og_type="website"):
    """Normalise a metadata payload for the base template."""
    return {
        "title": title,
        "description": description,
        "canonical": canonical,
        "robots": robots,
        "og_type": og_type,
        "image": image,
    }


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
class HomePageView(View):
    template_name = "seo/home.html"

    def get(self, request):
        meta = SEOService.default_metadata()
        meta["canonical"] = settings.SITE_URL + "/"
        featured = (
            Product.objects.public()
            .filter(noindex=False, is_featured=True)
            .select_related("category")[:8]
        )
        new_arrivals = (
            Product.objects.public()
            .filter(noindex=False, is_new_arrival=True)
            .select_related("category")
            .order_by("-created_at")[:8]
        )
        structured = _json_ld(
            SEOService.organisation_structured_data(),
            SEOService.website_structured_data(),
        )
        return _render(request, self.template_name, {
            "meta": _page_meta(
                meta["title"], meta["description"], meta["canonical"],
                image=meta.get("og", {}).get("image", ""),
            ),
            "structured_data": structured,
            "featured_products": featured,
            "new_arrivals": new_arrivals,
            "banners": SettingsService.active_banners()[:3],
            "page_heading": settings.BUSINESS_NAME,
        })


# ---------------------------------------------------------------------------
# Shop listing
# ---------------------------------------------------------------------------
class ShopPageView(View):
    template_name = "seo/shop.html"

    def get(self, request):
        if request.path != "/shop":
            # One canonical listing URL; duplicates are redirected, never served.
            suffix = f"?{request.META['QUERY_STRING']}" if request.META.get("QUERY_STRING") else ""
            return HttpResponsePermanentRedirect(f"{settings.SITE_URL}/shop{suffix}")

        page_number = _positive_int(request.GET.get("page"), 1)
        query = (request.GET.get("q") or "").strip()[:120]

        products = Product.objects.public().filter(noindex=False).select_related("category")
        if query:
            products = products.filter(
                Q(name__icontains=query)
                | Q(short_description__icontains=query)
                | Q(search_keywords__icontains=query)
            )
        total = products.count()
        offset = (page_number - 1) * PAGE_SIZE
        page_items = list(products.order_by("-created_at")[offset:offset + PAGE_SIZE])
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        canonical = f"{settings.SITE_URL}/shop" + (
            f"?page={page_number}" if page_number > 1 else ""
        )
        title = f"{query} — {settings.BUSINESS_NAME}" if query else f"Shop all — {settings.BUSINESS_NAME}"

        return _render(request, self.template_name, {
            "meta": _page_meta(
                title[:200],
                f"Browse {total} products from {settings.BUSINESS_NAME}. "
                "Electronics, fashion, home, beauty and more, delivered across Nigeria.",
                canonical,
            ),
            "structured_data": _json_ld(
                SEOService.breadcrumb_structured_data([
                    {"name": "Home", "url": "/"},
                    {"name": "Shop", "url": "/shop"},
                ]),
            ),
            "page_heading": "Shop all products",
            "products": page_items,
            "total": total,
            "page_number": page_number,
            "num_pages": pages,
            "query": query,
            "breadcrumbs": [{"name": "Home", "url": "/"}, {"name": "Shop", "url": "/shop"}],
        })


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
class CategoryPageView(View):
    template_name = "seo/category.html"

    def get(self, request, path: str):
        category = (
            Category.objects.public()
            .filter(Q(path=path) | Q(slug=path))
            .order_by("depth")
            .first()
        )
        # Accept a full materialised path ("electronics/phones") or a bare slug.
        if category is None and "/" in path:
            category = Category.objects.public().filter(path=path).first()
        if category is None:
            raise Http404("Category not found")

        meta = SEOService.category_metadata(category)
        canonical = meta["canonical"]
        # A category reached under a non-canonical path must not compete with itself.
        if request.path != category.absolute_path:
            return HttpResponsePermanentRedirect(canonical)

        page_number = _positive_int(request.GET.get("page"), 1)
        products = (
            Product.objects.public()
            .filter(category=category, noindex=False)
            .select_related("category")
        )
        total = products.count()
        offset = (page_number - 1) * PAGE_SIZE
        page_items = list(products.order_by("-created_at")[offset:offset + PAGE_SIZE])
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        return _render(request, self.template_name, {
            "meta": _page_meta(
                meta["title"], meta["description"], canonical,
                robots=meta["robots"],
                image=meta.get("og", {}).get("image", ""),
            ),
            "structured_data": _json_ld(
                meta["structured_data"],
                SEOService.breadcrumb_structured_data([
                    {"name": b["name"], "url": b["url"]} for b in meta["breadcrumbs"]
                ]),
            ),
            "category": category,
            "children": list(category.children.filter(
                is_active=True, status=PublishableModel.Status.PUBLISHED
            ).order_by("position", "name")),
            "products": page_items,
            "total": total,
            "page_number": page_number,
            "num_pages": pages,
            "breadcrumbs": meta["breadcrumbs"],
            "page_heading": category.name,
        })


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
class ProductPageView(View):
    template_name = "seo/product.html"

    def get(self, request, slug: str):
        product = (
            Product.objects.public()
            .select_related("category")
            .filter(slug=slug)
            .first()
        )
        if product is None:
            raise Http404("Product not found")

        meta = SEOService.product_metadata(product)
        canonical = meta["canonical"]
        if request.path != product.absolute_path:
            return HttpResponsePermanentRedirect(canonical)

        variations = []
        for variation in product.variations.filter(is_active=True).prefetch_related("attribute_values"):
            variations.append({
                "id": str(variation.pk),
                "sku": variation.sku,
                "label": " / ".join(v.value for v in variation.attribute_values.all()) or variation.sku,
                "price": variation.effective_price,
                "available": InventoryService.available_quantity(product, variation),
            })

        # Display-only stock signal; the authoritative check happens at
        # reservation time inside the inventory service.
        available = InventoryService.available_quantity(product)

        return _render(request, self.template_name, {
            "meta": _page_meta(
                meta["title"], meta["description"], canonical,
                robots=meta["robots"],
                image=meta.get("og", {}).get("image", ""),
                og_type="product",
            ),
            "structured_data": _json_ld(
                meta["structured_data"],
                SEOService.breadcrumb_structured_data([
                    {"name": b["name"], "url": b["url"]} for b in meta["breadcrumbs"]
                ]),
            ),
            "product": product,
            "variations": variations,
            "available": available,
            "in_stock": available > 0,
            "specifications": product.specifications or {},
            "key_features": product.key_features or [],
            "breadcrumbs": meta["breadcrumbs"],
            "page_heading": product.name,
        })


# ---------------------------------------------------------------------------
# CMS content pages
# ---------------------------------------------------------------------------
class ContentPageView(View):
    template_name = "seo/page.html"

    def get(self, request, slug: str):
        page = ContentPage.objects.filter(
            slug=slug, status=PublishableModel.Status.PUBLISHED
        ).first()
        if page is None:
            raise Http404("Page not found")

        title = page.meta_title or f"{page.title} — {settings.BUSINESS_NAME}"
        description = page.meta_description or page.excerpt or ""
        canonical = page.canonical_url or f"{settings.SITE_URL}{page.absolute_path}"
        if request.path != page.absolute_path:
            return HttpResponsePermanentRedirect(canonical)

        return _render(request, self.template_name, {
            "meta": _page_meta(
                title[:200], description[:320], canonical,
                robots="noindex,follow" if page.noindex else "index,follow",
            ),
            "structured_data": _json_ld(
                SEOService.breadcrumb_structured_data([
                    {"name": "Home", "url": "/"},
                    {"name": page.title, "url": page.absolute_path},
                ]),
            ),
            "content_page": page,
            "breadcrumbs": [
                {"name": "Home", "url": "/"},
                {"name": page.title, "url": page.absolute_path},
            ],
            "page_heading": page.title,
        })


# ---------------------------------------------------------------------------
# Redirects and the HTML 404
# ---------------------------------------------------------------------------
class RedirectFallbackView(View):
    """
    Last URL pattern: honours admin-managed redirects, otherwise renders a real
    404 page with the correct status code (never a soft 200).
    """

    def get(self, request, path: str = ""):
        target = SEOService.resolve_redirect("/" + path)
        if target is not None:
            to_path, status_code = target
            redirect_class = HttpResponsePermanentRedirect if status_code == 301 else HttpResponseRedirect
            return redirect_class(to_path)
        response = _render(request, "seo/404.html", {
            "meta": _page_meta(
                "Page not found — " + settings.BUSINESS_NAME,
                "The page you were looking for does not exist.",
                settings.SITE_URL + "/",
                robots="noindex,nofollow",
            ),
            "structured_data": "",
            "page_heading": "Page not found",
        }, status=404)
        return response


# ---------------------------------------------------------------------------
def _positive_int(raw, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= 1 else default


# ---------------------------------------------------------------------------
# Error handlers (wired through config.urls: handler404 / handler500)
# ---------------------------------------------------------------------------
def not_found_response(request):
    return _render(request, "seo/404.html", {
        "meta": _page_meta(
            "Page not found — " + settings.BUSINESS_NAME,
            "The page you were looking for does not exist.",
            settings.SITE_URL + "/",
            robots="noindex,nofollow",
        ),
        "structured_data": "",
        "page_heading": "Page not found",
    }, status=404)


def server_error_response(request):
    return _render(request, "seo/500.html", {
        "meta": _page_meta(
            "Something went wrong — " + settings.BUSINESS_NAME,
            "An unexpected error occurred. Please try again.",
            settings.SITE_URL + "/",
            robots="noindex,nofollow",
        ),
        "structured_data": "",
        "page_heading": "Something went wrong",
    }, status=500)
