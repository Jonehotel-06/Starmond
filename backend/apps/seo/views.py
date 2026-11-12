"""SEO surfaces: per-path metadata, sitemap.xml and robots.txt."""
from __future__ import annotations

from django.http import HttpResponse
from django.views import View
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.core.views import BaseAPIView
from apps.seo.models import SEOSetting
from apps.seo.services import SEOService


class MetadataView(BaseAPIView):
    """Metadata for any public path so the frontend can render a correct <head>."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request):
        path = request.query_params.get("path", "/")
        if SEOService.is_private_path(path):
            return self.ok({
                "title": "STARMOND", "description": "", "canonical": "",
                "robots": "noindex,nofollow", "og": {}, "twitter": {},
            })
        payload = SEOService.for_path(path)
        payload["structured_data_defaults"] = {
            "organization": SEOService.organisation_structured_data(),
            "website": SEOService.website_structured_data(),
        }
        return self.ok(payload)


class SitemapXmlView(View):
    """Crawlable XML sitemap — drafts, noindex pages and APIs are excluded."""

    def get(self, request, *args, **kwargs):
        return HttpResponse(
            SEOService.sitemap_xml(), content_type="application/xml; charset=utf-8"
        )


class RobotsTxtView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse(SEOService.robots_txt(), content_type="text/plain; charset=utf-8")


class SEOSettingsListView(BaseAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        rows = SEOSetting.objects.filter(is_active=True)
        return self.ok([
            {
                "path": row.path, "title": row.title, "description": row.description,
                "canonical_url": row.canonical_url, "robots": row.robots,
            }
            for row in rows
        ])
