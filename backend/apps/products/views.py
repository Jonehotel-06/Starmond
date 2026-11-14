import django_filters as filters
from django.db.models import Avg, Case, Count, F, IntegerField, Q, Sum, Value, When
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.audit.services import AuditService
from apps.categories.models import Category
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission
from apps.inventory.models import Inventory

from .models import Product, ProductImage, ProductVariation
from .serializers import (
    ProductImageSerializer,
    ProductPublicDetailSerializer,
    ProductStaffSerializer,
    ProductVariationStaffSerializer,
    _BaseProductFields,
)
from .services import ProductService


def _stock_annotation(qs):
    """Annotate total available stock per product in SQL (avoids N+1)."""
    return qs.annotate(annotated_available=Sum(F("inventory_records__on_hand") - F("inventory_records__reserved")))


class ProductPublicFilter(filters.FilterSet):
    category = filters.CharFilter(method="filter_category")
    min_price = filters.NumberFilter(field_name="effective_price_sql", method="filter_min_price")
    max_price = filters.NumberFilter(method="filter_max_price")
    featured = filters.BooleanFilter(field_name="is_featured")
    new_arrivals = filters.BooleanFilter(field_name="is_new_arrival")
    best_sellers = filters.BooleanFilter(field_name="is_best_seller")
    brand = filters.CharFilter(field_name="brand", lookup_expr="iexact")
    in_stock = filters.BooleanFilter(method="filter_in_stock")
    q = filters.CharFilter(method="filter_q")

    class Meta:
        model = Product
        fields = ["category", "featured", "new_arrivals", "best_sellers", "brand", "in_stock", "min_price", "max_price"]

    def filter_category(self, qs, name, value):
        category = Category.objects.filter(Q(slug=value) | Q(pk=value if str(value).isdigit() else 0)).first()
        if not category:
            return qs.none()
        ids = [category.pk] + [c.pk for c in Category.objects.filter(parent=category)]
        # include deeper descendants
        frontier, seen = list(Category.objects.filter(parent=category)), set(ids)
        while frontier:
            node = frontier.pop()
            if node.pk not in seen:
                ids.append(node.pk)
                seen.add(node.pk)
            frontier.extend(Category.objects.filter(parent=node))
        return qs.filter(category_id__in=ids)

    def _price_expr(self):
        from django.db.models.functions import Coalesce
        return Coalesce("sale_price", "regular_price")

    def filter_min_price(self, qs, name, value):
        return qs.annotate(_price=self._price_expr()).filter(_price__gte=value)

    def filter_max_price(self, qs, name, value):
        return qs.annotate(_price=self._price_expr()).filter(_price__lte=value)

    def filter_in_stock(self, qs, name, value):
        qs = _stock_annotation(qs)
        return qs.filter(annotated_available__gt=0) if value else qs.filter(Q(annotated_available__lte=0) | Q(annotated_available__isnull=True))

    def filter_q(self, qs, name, value):
        return qs.filter(
            Q(name__icontains=value) | Q(short_description__icontains=value) |
            Q(description__icontains=value) | Q(sku__icontains=value) |
            Q(brand__icontains=value) | Q(tags__icontains=value) |
            Q(category__name__icontains=value)
        )


class PublicProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Public storefront product APIs. Only active products are returned;
    prices and stock always come from the database — never from the client."""
    permission_classes = [AllowAny]
    serializer_class = _BaseProductFields
    filterset_class = ProductPublicFilter
    lookup_field = "slug"
    lookup_value_regex = "[^/]+"
    ordering_fields = ["created_at", "name", "regular_price"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return _stock_annotation(
            Product.objects.public()
            .select_related("category__parent__parent")
            .prefetch_related("images")
            .annotate(
                avg_rating=Avg("reviews__rating", filter=Q(reviews__moderation_status="approved")),
                review_count=Count("reviews", filter=Q(reviews__moderation_status="approved"), distinct=True),
            )
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductPublicDetailSerializer
        return _BaseProductFields

    def retrieve(self, request, *args, **kwargs):
        product = get_object_or_404(
            Product.objects.public().select_related("category__parent__parent")
            .prefetch_related("images", "attributes__values", "variations__image",
                              "variations__inventory_record"), slug=kwargs["slug"])
        return Response({
            "status": "success",
            "data": self.get_serializer(product, context={"request": request}).data,
            "seo": product.effective_seo(),
        })


@extend_schema(tags=["products"], responses=OpenApiTypes.OBJECT,
    description="Case-insensitive partial search over name, description, SKU, brand, category, attributes and tags. Returns paginated results plus name suggestions.")
class ProductSearchView(viewsets.ViewSet):
    """GET /api/products/search/?q=...&category=<slug>&page=...

    Case-insensitive partial search over name, description, SKU, brand,
    category and tags, with name-weighted ordering and suggestions.
    """
    permission_classes = [AllowAny]

    def list(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response({"status": "success", "count": 0, "results": [], "suggestions": []})
        qs = _stock_annotation(
            Product.objects.public().select_related("category__parent__parent").prefetch_related("images")
            .annotate(avg_rating=Avg("reviews__rating", filter=Q(reviews__moderation_status="approved")),
                      review_count=Count("reviews", filter=Q(reviews__moderation_status="approved"), distinct=True)))
        category_slug = request.query_params.get("category")
        if category_slug:
            qs = ProductPublicFilter().filter_category(qs, "category", category_slug)
        qs = qs.filter(
            Q(name__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q) |
            Q(sku__icontains=q) | Q(brand__icontains=q) | Q(tags__icontains=q) |
            Q(category__name__icontains=q) | Q(attributes__name__icontains=q) |
            Q(attributes__values__value__icontains=q)
        ).distinct().annotate(
            name_match=Case(When(name__istartswith=q, then=Value(2)), When(name__icontains=q, then=Value(1)),
                            default=Value(0), output_field=IntegerField())
        ).order_by("-name_match", "-annotated_available", "-created_at")[:100]

        from apps.core.pagination import StandardPagination
        paginator = StandardPagination()
        page = paginator.paginate_queryset(list(qs), request, view=self)
        data = _BaseProductFields(page, many=True, context={"request": request}).data
        suggestions = list(
            Product.objects.public().filter(name__icontains=q).values_list("name", flat=True).distinct()[:8]
        )
        response = paginator.get_paginated_response(data)
        response.data["suggestions"] = suggestions
        return response


class StaffProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]

    @property
    def permission_codename(self):
        """Reads require products.view; writes require products.manage."""
        if getattr(self, "request", None) and self.request.method in ("GET", "HEAD", "OPTIONS"):
            return Perm.PRODUCTS_VIEW
        return Perm.PRODUCTS_MANAGE
    serializer_class = ProductStaffSerializer
    parser_classes = [MultiPartParser, JSONParser]
    queryset = Product.objects.select_related("category").prefetch_related(
        "images", "variations__inventory_record", "attributes__values").all()
    filterset_fields = ["status", "is_active", "is_featured", "category"]
    search_fields = ["name", "sku", "brand"]
    ordering = ["-created_at", "name"]
    http_method_names = ["get", "post", "patch", "put", "delete"]

    def create(self, request, *args, **kwargs):
        payload = self._product_payload(request.data)
        product = Product()
        ProductService.create_or_update(product, payload)
        self._after_save(product, request.data, request)
        AuditService.log(request.user, "product.create", "Product", product.pk, {"sku": product.sku}, request=request)
        return Response({"status": "success", "data": self.get_serializer(product).data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        product = self.get_object()
        payload = self._product_payload(request.data, partial=kwargs.pop("partial", False), instance=product)
        ProductService.create_or_update(product, payload)
        self._after_save(product, request.data, request)
        AuditService.log(request.user, "product.update", "Product", product.pk, {"sku": product.sku}, request=request)
        return Response({"status": "success", "data": self.get_serializer(product).data})

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        result = ProductService.safe_delete(product)
        AuditService.log(request.user, f"product.{result}", "Product", product.pk, {"sku": product.sku}, request=request)
        return Response({"status": "success", "message": f"Product {result}.", "data": {"result": result}})

    # ------------------------------------------------------------- helpers
    def _product_payload(self, data, partial=False, instance=None):
        editable = [
            "name", "sku", "category", "short_description", "description", "regular_price",
            "sale_price", "cost_price", "low_stock_threshold", "status", "is_featured",
            "is_new_arrival", "is_best_seller", "weight_kg", "length_cm", "width_cm",
            "height_cm", "brand", "tags", "specifications", "video_url",
            "supports_customization", "customization_schema",
            "seo_title", "seo_description", "seo_keywords", "canonical_url",
        ]
        payload = {}
        for field in editable:
            if field in data:
                value = data[field]
                if field in ("is_featured", "is_new_arrival", "is_best_seller", "supports_customization"):
                    value = str(value).lower() in ("true", "1", "yes", "on", True)
                payload[field] = value
        if not partial and not instance:
            for required in ("name", "sku", "category", "regular_price"):
                if required not in payload or payload[required] in (None, ""):
                    raise ServiceError(f"{required} is required.", code="required_field", fields={required: "This field is required."})
        return payload

    def _after_save(self, product, data, request):
        from apps.inventory.services import InventoryService
        stock = data.get("stock_quantity")
        if stock is not None:
            InventoryService.ensure_inventory(product, None, opening=int(stock))
        else:
            InventoryService.ensure_inventory(product, None)
        for key in ("og_image",):
            if key in data and data[key]:
                setattr(product, key, data[key])
                product.save(update_fields=[key, "updated_at"])

    # ------------------------------------------------------------- images
    @action(detail=True, methods=["post"], url_path="images", parser_classes=[MultiPartParser])
    def upload_images(self, request, pk=None):
        product = self.get_object()
        files = request.FILES.getlist("images") or ([request.FILES["file"]] if "file" in request.FILES else [])
        if not files:
            raise ServiceError("No image files provided (field: images[] or file).", code="missing_files")
        alt_text = request.data.get("alt_text", "")
        created = []
        from apps.media.services import MediaService, MediaValidationError
        has_main = product.images.filter(is_main=True).exists()
        for f in files[:10]:
            try:
                MediaService.validate_image(f)
            except MediaValidationError as exc:
                raise ServiceError(str(exc), code="invalid_media")
            image = ProductImage.objects.create(
                product=product, file=f, alt_text=alt_text or product.name,
                is_main=not has_main, sort_order=product.images.count())
            has_main = True
            created.append(image)
        AuditService.log(request.user, "product.images.upload", "Product", product.pk, {"count": len(created)}, request=request)
        return Response({"status": "success", "data": ProductImageSerializer(created, many=True).data}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request, pk=None):
        product = self.get_object()
        image_ids = request.data.get("image_ids", [])
        ProductService.reorder_images(product, image_ids)
        return Response({"status": "success", "message": "Image order updated."})

    @action(detail=True, methods=["post"], url_path="images/(?P<image_id>[0-9]+)/set-main")
    def set_main_image(self, request, pk=None, image_id=None):
        product = self.get_object()
        image = get_object_or_404(ProductImage, pk=image_id, product=product)
        ProductService.set_main_image(product, image)
        return Response({"status": "success", "message": "Main image updated."})

    @action(detail=True, methods=["delete"], url_path="images/(?P<image_id>[0-9]+)")
    def delete_image(self, request, pk=None, image_id=None):
        product = self.get_object()
        image = get_object_or_404(ProductImage, pk=image_id, product=product)
        was_main = image.is_main
        image.delete()
        if was_main:
            nxt = product.images.order_by("sort_order", "id").first()
            if nxt:
                ProductService.set_main_image(product, nxt)
        return Response({"status": "success", "message": "Image deleted."})

    # ------------------------------------------------------------- variations
    @action(detail=True, methods=["post"], url_path="variations")
    def upsert_variation(self, request, pk=None):
        product = self.get_object()
        data = dict(request.data)
        from .services import ProductService as PS
        variation = PS.upsert_variation(product, data)
        AuditService.log(request.user, "product.variation.upsert", "ProductVariation", variation.pk,
                         {"product": product.sku, "variation_sku": variation.sku}, request=request)
        return Response({"status": "success", "data": ProductVariationStaffSerializer(variation).data},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path="variations/(?P<variation_id>[0-9]+)")
    def delete_variation(self, request, pk=None, variation_id=None):
        product = self.get_object()
        variation = get_object_or_404(ProductVariation, pk=variation_id, product=product)
        from apps.orders.models import OrderItem
        if OrderItem.objects.filter(variation=variation).exists():
            variation.is_available = False
            variation.save(update_fields=["is_available", "updated_at"])
            return Response({"status": "success", "message": "Variation has order history — marked unavailable instead of deleted."})
        variation.delete()
        return Response({"status": "success", "message": "Variation deleted."})

    # ------------------------------------------------------------- status
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        product = self.get_object()
        product.status = Product.Status.ACTIVE
        product.is_active = True
        product.save(update_fields=["status", "is_active", "updated_at"])
        from apps.inventory.services import InventoryService
        InventoryService.sync_product_status(product)
        AuditService.log(request.user, "product.activate", "Product", product.pk, {}, request=request)
        return Response({"status": "success", "message": "Product activated."})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        product = self.get_object()
        product.status = Product.Status.INACTIVE
        product.is_active = False
        product.save(update_fields=["status", "is_active", "updated_at"])
        AuditService.log(request.user, "product.deactivate", "Product", product.pk, {}, request=request)
        return Response({"status": "success", "message": "Product deactivated."})

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        product = self.get_object()
        product.status = Product.Status.ARCHIVED
        product.is_active = False
        product.save(update_fields=["status", "is_active", "updated_at"])
        AuditService.log(request.user, "product.archive", "Product", product.pk, {}, request=request)
        return Response({"status": "success", "message": "Product archived."})
