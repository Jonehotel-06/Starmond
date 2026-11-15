from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission
from apps.products.models import Product
from apps.products.serializers import _BaseProductFields

from .models import Banner, HomepageSection, Page
from .serializers import (
    BannerSerializer,
    BusinessSettingsSerializer,
    HomepageSectionSerializer,
    PageSerializer,
)
from .services import BusinessSettingsService


from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view

@extend_schema(tags=["cms"], responses=OpenApiTypes.OBJECT)
class PublicSettingsView(APIView):
    """GET /api/cms/settings/ — public-safe business settings (no secrets)."""
    permission_classes = [AllowAny]

    def get(self, request):
        values = BusinessSettingsService.all_values()
        public = {k: values.get(k) for k in (
            "business_name", "business_description", "contact_email", "contact_phone",
            "business_address", "currency", "currency_symbol", "social_links", "logo_key",
            "favicon_key", "homepage_hero", "footer_text", "support_hours")}
        from .serializers import _public_media_url
        public["logo_url"] = _public_media_url(public.get("logo_key"))
        public["favicon_url"] = _public_media_url(public.get("favicon_key"))
        hero = dict(public.get("homepage_hero") or {})
        hero["image_url"] = _public_media_url(hero.get("image_key"))
        public["homepage_hero"] = hero
        return Response({"status": "success", "data": public})


class PublicPageViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PageSerializer
    queryset = Page.objects.filter(is_published=True)
    lookup_field = "slug"
    pagination_class = None

    def list(self, request, *args, **kwargs):
        return Response({"status": "success", "data": self.get_serializer(self.get_queryset(), many=True).data})

    def retrieve(self, request, *args, **kwargs):
        page = self.get_object()
        return Response({"status": "success", "data": self.get_serializer(page).data, "seo": page.effective_seo()})


@extend_schema(tags=["cms"], responses=OpenApiTypes.OBJECT)
class HomepageView(APIView):
    """GET /api/cms/homepage/ — small, cache-friendly homepage payload:
    sections, banners and limited product rows (never the full catalogue)."""
    permission_classes = [AllowAny]

    def get(self, request):
        from django.core.cache import cache
        from django.conf import settings
        cached = cache.get("cms:homepage")
        if cached:
            return Response({"status": "success", "data": cached, "cached": True})
        now = timezone.now()
        sections = HomepageSection.objects.filter(is_active=True)
        banners = Banner.objects.filter(is_active=True).filter(
            models_q_now(now)).order_by("display_order")[:6]
        data = {
            "settings": {k: BusinessSettingsService.all_values().get(k) for k in
                         ("business_name", "homepage_hero", "currency_symbol")},
            "sections": HomepageSectionSerializer(sections, many=True).data,
            "banners": BannerSerializer(banners, many=True).data,
            "featured": _BaseProductFields(
                Product.objects.public().filter(is_featured=True).select_related("category")[:8], many=True).data,
            "new_arrivals": _BaseProductFields(
                Product.objects.public().filter(is_new_arrival=True).select_related("category")[:8], many=True).data,
        }
        cache.set("cms:homepage", data, settings.CACHE_TTL_SHORT)
        return Response({"status": "success", "data": data, "cached": False})


def models_q_now(now):
    from django.db.models import Q
    return (Q(starts_at__isnull=True) | Q(starts_at__lte=now)) & (Q(ends_at__isnull=True) | Q(ends_at__gte=now))


@extend_schema_view(
    get=extend_schema(tags=["cms"], responses=OpenApiTypes.OBJECT),
    patch=extend_schema(tags=["cms"], request=BusinessSettingsSerializer, responses=OpenApiTypes.OBJECT))
class StaffSettingsView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.SETTINGS_MANAGE

    def get(self, request):
        return Response({"status": "success", "data": BusinessSettingsService.all_values(use_cache=False)})

    def patch(self, request):
        serializer = BusinessSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = BusinessSettingsService.update(serializer.validated_data["values"], user=request.user)
        AuditService.log(request.user, "settings.update", "BusinessSetting", "1", {"keys": list(serializer.validated_data["values"].keys())}, request=request)
        return Response({"status": "success", "data": values})


class StaffPageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.CMS_MANAGE
    serializer_class = PageSerializer
    queryset = Page.objects.all()
    lookup_field = "slug"


class StaffHomepageSectionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.CMS_MANAGE
    serializer_class = HomepageSectionSerializer
    queryset = HomepageSection.objects.all()
    pagination_class = None


class StaffBannerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.CMS_MANAGE
    serializer_class = BannerSerializer
    queryset = Banner.objects.all()
    pagination_class = None
