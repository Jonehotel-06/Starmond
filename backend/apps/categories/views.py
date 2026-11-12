"""Public category endpoints — tree, detail, breadcrumbs, SEO metadata."""
from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.categories.models import Category
from apps.categories.serializers import CategoryDetailSerializer, CategoryListSerializer
from apps.categories.services import CategoryService
from apps.core.pagination import StandardResultsSetPagination
from apps.core.views import BaseAPIView
from apps.seo.services import SEOService


class CategoryTreeView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request):
        return self.ok({
            "tree": CategoryService.tree(public_only=True),
            "featured": CategoryListSerializer(CategoryService.featured(), many=True).data,
            "seo": SEOService.for_path("/shop"),
        })


class CategoryListView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request):
        queryset = Category.objects.public().filter(parent__isnull=True).order_by("position", "name")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            CategoryListSerializer(page, many=True).data
        )


class CategoryDetailView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request, slug: str):
        category = CategoryService.get_public(slug)
        payload = CategoryDetailSerializer(category).data
        payload["seo"] = SEOService.category_metadata(category)
        return self.ok(payload)
