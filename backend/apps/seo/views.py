from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.categories.models import Category
from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission
from apps.products.models import Product

from .services import SEOService

ROBOTS_TXT = """User-agent: *
Allow: /
Disallow: /api/
Disallow: /django-admin/
Disallow: /cart
Disallow: /checkout
Disallow: /account/

Sitemap: {sitemap_url}
"""


def robots_txt_view(request):
    sitemap_url = request.build_absolute_uri("/sitemap.xml")
    return HttpResponse(ROBOTS_TXT.format(sitemap_url=sitemap_url), content_type="text/plain; charset=utf-8")


def sitemap_xml_view(request):
    entries = SEOService.sitemap_entries()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for e in entries[:45000]:
        lastmod = e["lastmod"].date().isoformat() if e["lastmod"] else ""
        lines.append(
            "  <url><loc>{}</loc>{}<changefreq>{}</changefreq><priority>{}</priority></url>".format(
                _escape(e["loc"]),
                f"<lastmod>{lastmod}</lastmod>" if lastmod else "",
                e["changefreq"], e["priority"]))
    lines.append("</urlset>")
    return HttpResponse("\n".join(lines), content_type="application/xml; charset=utf-8")


def _escape(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view

@extend_schema(tags=["seo"], responses=OpenApiTypes.OBJECT)
class StructuredDataView(APIView):
    """GET /api/seo/structured-data/organization/ | website/ | product/<slug>/ |
    breadcrumbs/?category=<slug>&product=<slug>"""
    permission_classes = [AllowAny]

    def get(self, request, kind, slug=None):
        if kind == "organization":
            return Response({"status": "success", "data": SEOService.organization_ld()})
        if kind == "website":
            return Response({"status": "success", "data": SEOService.website_ld()})
        if kind == "product":
            product = get_object_or_404(Product.objects.public().select_related("category__parent"), slug=slug)
            data = [SEOService.product_ld(product),
                    SEOService.breadcrumb_ld(product.category.breadcrumb + [{"name": product.name, "url_path": product.url_path}])]
            return Response({"status": "success", "data": data})
        if kind == "breadcrumbs":
            category_slug = request.query_params.get("category")
            items = [{"name": "Home", "url_path": "/"}]
            if category_slug:
                category = get_object_or_404(Category.objects.active(), slug=category_slug)
                items += category.breadcrumb
            return Response({"status": "success", "data": SEOService.breadcrumb_ld(items)})
        return Response({"status": "error", "error": {"code": "unknown_kind", "message": "Unknown structured data kind.", "fields": None}}, status=404)


@extend_schema_view(
    get=extend_schema(tags=["seo"], responses=OpenApiTypes.OBJECT),
    patch=extend_schema(tags=["seo"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT))
class SEOSettingsStaffView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.SEO_MANAGE

    def get(self, request):
        return Response({"status": "success", "data": SEOService.settings_values()})

    def patch(self, request):
        values = SEOService.update_settings(request.data or {})
        AuditService.log(request.user, "seo.settings.update", "SEOSetting", "1", {"keys": list((request.data or {}).keys())}, request=request)
        return Response({"status": "success", "data": values})


@extend_schema(tags=["seo"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class SEOPreviewSnippetView(APIView):
    """POST /api/seo/preview-snippet/ — search-result snippet preview for staff."""
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.SEO_MANAGE

    def post(self, request):
        title = (request.data.get("title") or "")[:180]
        description = (request.data.get("description") or "")[:320]
        url = (request.data.get("url") or "")[:300]
        warnings = []
        if len(title) > 60:
            warnings.append("Title longer than ~60 characters may be truncated in search results.")
        if len(description) > 160:
            warnings.append("Meta description longer than ~160 characters may be truncated.")
        if not title:
            warnings.append("Title is empty.")
        if not description:
            warnings.append("Description is empty.")
        return Response({"status": "success", "data": {
            "preview": {"title": title, "url": url, "description": description},
            "title_length": len(title), "description_length": len(description),
            "warnings": warnings,
        }})


@extend_schema_view(
    get=extend_schema(tags=["seo"], responses=OpenApiTypes.OBJECT),
    patch=extend_schema(tags=["seo"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT))
class ProductSEOStaffView(APIView):
    """PATCH /api/seo/products/<slug>/ — update product SEO fields."""
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.SEO_MANAGE

    def get(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        return Response({"status": "success", "data": {
            "slug": product.slug, "seo": product.effective_seo(),
            "raw": {"seo_title": product.seo_title, "seo_description": product.seo_description,
                    "seo_keywords": product.seo_keywords, "canonical_url": product.canonical_url},
        }})

    def patch(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        allowed = ("seo_title", "seo_description", "seo_keywords", "canonical_url")
        changed = {}
        for field in allowed:
            if field in request.data:
                setattr(product, field, (request.data[field] or "")[:400])
                changed[field] = request.data[field]
        if "og_image" in request.data:
            changed["og_image"] = "(set via product admin upload)"
        product.save(update_fields=list(changed.keys()) + ["updated_at"] if changed else ["updated_at"])
        SEOService.touch()
        AuditService.log(request.user, "seo.product.update", "Product", product.pk, changed, request=request)
        return Response({"status": "success", "data": product.effective_seo()})


@extend_schema_view(
    get=extend_schema(tags=["seo"], responses=OpenApiTypes.OBJECT),
    patch=extend_schema(tags=["seo"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT))
class CategorySEOStaffView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.SEO_MANAGE

    def get(self, request, slug):
        category = get_object_or_404(Category, slug=slug)
        return Response({"status": "success", "data": {"slug": category.slug, "seo": category.effective_seo()}})

    def patch(self, request, slug):
        category = get_object_or_404(Category, slug=slug)
        allowed = ("seo_title", "seo_description", "seo_keywords", "canonical_url")
        changed = {}
        for field in allowed:
            if field in request.data:
                setattr(category, field, (request.data[field] or "")[:400])
                changed[field] = request.data[field]
        if changed:
            category.save(update_fields=list(changed.keys()) + ["updated_at"])
        SEOService.touch()
        AuditService.log(request.user, "seo.category.update", "Category", category.pk, changed, request=request)
        return Response({"status": "success", "data": category.effective_seo()})
