"""Public storefront configuration and editable content pages."""
from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.cms.models import BusinessSetting, ContentPage
from apps.cms.services import SettingsService
from apps.core.exceptions import NotFound
from apps.core.models import PublishableModel
from apps.core.permissions import IsStaff
from apps.core.views import BaseAPIView
from apps.seo.services import SEOService


class PublicSettingsView(BaseAPIView):
    """Everything the frontend needs to render store branding, contact and policy links."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request):
        return self.ok({
            "settings": SettingsService.all(public_only=True),
            "banners": SettingsService.active_banners(),
            "pages": SettingsService.public_pages(),
            "pickup_locations": SettingsService.pickup_locations(),
            "structured_data": {
                "organization": SEOService.organisation_structured_data(),
                "website": SEOService.website_structured_data(),
            },
        })


class ContentPageDetailView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request, slug: str):
        page = ContentPage.objects.filter(
            slug=slug, status=PublishableModel.Status.PUBLISHED
        ).first()
        if page is None:
            raise NotFound("Page not found.")
        return self.ok({
            "slug": page.slug,
            "title": page.title,
            "subtitle": page.subtitle,
            "body": page.body,
            "excerpt": page.excerpt,
            "hero_image": page.hero_image.url if page.hero_image else None,
            "updated_at": page.updated_at,
            "seo": {
                "title": page.meta_title or page.title,
                "description": page.meta_description or page.excerpt,
                "canonical": page.canonical_url or f"/page/{page.slug}",
                "robots": "noindex,nofollow" if page.noindex else "index,follow",
            },
        })


class StaffSettingsUpdateView(BaseAPIView):
    permission_classes = [IsStaff]

    def get(self, request):
        return self.ok({"settings": SettingsService.grouped(public_only=False)})

    def patch(self, request):
        values = request.data.get("settings") or request.data
        if not isinstance(values, dict):
            from apps.core.exceptions import ValidationError

            raise ValidationError("Settings must be submitted as an object.")
        updated = SettingsService.update_many(values, actor=request.user)
        return self.ok({"updated": updated}, message="Settings saved.")
