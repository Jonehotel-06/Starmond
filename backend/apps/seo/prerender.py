"""Server-rendered crawlable HTML for public /shop/ URLs.

The storefront frontend is pure HTML/CSS/JS and cannot guarantee that the
initial HTML contains catalogue content for crawlers. These views render
minimal, semantic, indexable pages (metadata + JSON-LD + real catalogue data)
directly from the backend database. They are NOT the storefront UI and use no
frontend framework.
"""
import json

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from apps.categories.models import Category
from apps.products.models import Product
from apps.reviews.services import ReviewService

from .services import SEOService


def _enabled():
    return bool(SEOService.settings_values().get("enable_prerender", True))


@cache_page(300)
def shop_path_view(request, path=""):
    if not _enabled():
        raise Http404()
    segments = [s for s in (path or "").split("/") if s]
    if not segments:
        return _render_category(request, None)
    slug = segments[-1]
    product = Product.objects.public().select_related("category__parent").filter(slug=slug).first()
    if product:
        return _render_product(request, product)
    category = _resolve_category(segments)
    if category:
        return _render_category(request, category)
    raise Http404()


def _resolve_category(segments):
    """Match /shop/a/b/c/ against nested category slugs."""
    node = None
    for seg in segments:
        qs = Category.objects.active()
        qs = qs.filter(parent=node) if node else qs.filter(parent__isnull=True)
        node = qs.filter(slug=seg).first()
        if not node:
            return None
    return node


def _render_category(request, category):
    if category is None:
        categories = Category.objects.active().roots()
        products = Product.objects.public().select_related("category")[:40]
        meta = SEOService.page_meta(
            title="Shop all categories",
            description="Browse electrical supplies, fashion, electronics, gadgets and home products.",
            canonical=f"{settings.SITE_URL}/shop/")
        return render(request, "seo/prerender_category.html", {
            "meta": meta, "category": _FakeRoot(), "subcategories": categories,
            "products": products, "breadcrumb_json": json.dumps(
                SEOService.breadcrumb_ld([{"name": "Home", "url_path": "/"}, {"name": "Shop", "url_path": "/shop/"}]))})
    subcategories = category.children.filter(is_active=True)
    products = Product.objects.public().filter(category=category).select_related("category")[:60]
    seo = category.effective_seo()
    meta = SEOService.page_meta(
        title=seo["title"], description=seo["description"],
        canonical=seo["canonical_url"] or f"{settings.SITE_URL}{category.url_path}",
        og_image=seo["og_image"])
    crumbs = [{"name": "Home", "url_path": "/"}, {"name": "Shop", "url_path": "/shop/"}] + category.breadcrumb
    return render(request, "seo/prerender_category.html", {
        "meta": meta, "category": category, "subcategories": subcategories, "products": products,
        "breadcrumb_json": json.dumps(SEOService.breadcrumb_ld(crumbs))})


class _FakeRoot:
    name = "All categories"
    description = ""
    breadcrumb = [{"name": "Home", "url_path": "/"}, {"name": "Shop", "url_path": "/shop/"}]


def _render_product(request, product):
    seo = product.effective_seo()
    meta = SEOService.page_meta(
        title=seo["title"], description=seo["description"],
        canonical=seo["canonical_url"] or f"{settings.SITE_URL}{product.url_path}",
        og_image=seo["og_image"], entity_type="product")
    main_image = product.main_image
    crumbs = [{"name": "Home", "url_path": "/"}, {"name": "Shop", "url_path": "/shop/"}] + product.category.breadcrumb + \
             [{"name": product.name, "url_path": product.url_path}]
    return render(request, "seo/prerender_product.html", {
        "meta": meta, "product": product,
        "main_image": main_image.file_url if main_image else None,
        "variations": product.variations.all()[:30],
        "specifications": product.specifications or {},
        "rating_summary": ReviewService.product_summary(product),
        "breadcrumbs": crumbs,
        "product_json": json.dumps(SEOService.product_ld(product)),
        "breadcrumb_json": json.dumps(SEOService.breadcrumb_ld(crumbs)),
    })
