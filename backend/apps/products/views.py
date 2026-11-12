"""Public product endpoints: listing, search, detail, facets."""
from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.categories.models import Category
from apps.core.exceptions import ValidationError
from apps.core.pagination import StandardResultsSetPagination
from apps.core.views import BaseAPIView
from apps.products.models import Brand, ProductAttribute
from apps.products.serializers import (
    AttributeSerializer, BrandSerializer, ProductDetailSerializer, ProductListSerializer,
)
from apps.products.services import ProductService


class ProductListView(BaseAPIView):
    """Paginated catalogue browsing with filters and ordering."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"

    def get(self, request):
        params = request.query_params
        category = None
        if params.get("category"):
            category = Category.objects.public().filter(slug=params["category"]).first()
            if category is None:
                raise ValidationError("The requested category does not exist.")

        brand_ids = [b for b in params.getlist("brand") if b]
        featured = params.get("featured")
        queryset = ProductService.search(
            query=params.get("q", ""),
            category=category,
            min_price=params.get("min_price") or None,
            max_price=params.get("max_price") or None,
            in_stock_only=params.get("in_stock") in {"1", "true", "yes"},
            featured=(featured.lower() == "true") if featured is not None else None,
            sort=params.get("sort", "newest"),
            brand_ids=brand_ids or None,
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            ProductListSerializer(page, many=True, context={"request": request}).data
        )


class ProductDetailView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request, slug: str):
        product = ProductService.get_public_product(slug)
        ProductService.increment_view(product)
        return self.ok(ProductDetailSerializer(product, context={"request": request}).data)


class ProductSearchView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return self.ok({"results": [], "count": 0, "facets": {}, "query": query})
        queryset = ProductService.search(query=query, sort=request.query_params.get("sort", ""))
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            ProductListSerializer(page, many=True, context={"request": request}).data
        )


class FeaturedProductsView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request):
        from apps.products.models import Product

        limit = min(int(request.query_params.get("limit", 12) or 12), 48)
        return self.ok({
            "featured": ProductListSerializer(
                Product.objects.featured().prefetch_related("images")[:limit], many=True
            ).data,
            "new_arrivals": ProductListSerializer(
                Product.objects.new_arrivals().prefetch_related("images")[:limit], many=True
            ).data,
            "best_sellers": ProductListSerializer(
                Product.objects.best_sellers().prefetch_related("images")[:limit], many=True
            ).data,
        })


class ProductFacetsView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request):
        category = None
        if request.query_params.get("category"):
            category = Category.objects.public().filter(
                slug=request.query_params["category"]
            ).first()
        return self.ok({
            "facets": ProductService.catalogue_facets(category),
            "brands": BrandSerializer(Brand.objects.filter(is_active=True), many=True).data,
            "attributes": AttributeSerializer(
                ProductAttribute.objects.prefetch_related("values"), many=True
            ).data,
        })
