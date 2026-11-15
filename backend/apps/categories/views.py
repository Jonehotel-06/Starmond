import django_filters as filters
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission

from .models import Category
from .serializers import CategoryPublicSerializer, CategoryStaffSerializer
from .services import CategoryService


class CategoryPublicFilter(filters.FilterSet):
    parent = filters.NumberFilter(field_name="parent_id")
    root = filters.BooleanFilter(method="filter_root")

    class Meta:
        model = Category
        fields = ["parent", "root"]

    def filter_root(self, queryset, name, value):
        return queryset.filter(parent__isnull=True) if value else queryset


class PublicCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Public storefront category browsing. Only active categories."""
    permission_classes = [AllowAny]
    serializer_class = CategoryPublicSerializer
    filterset_class = CategoryPublicFilter
    lookup_field = "slug"
    lookup_value_regex = "[^/]+"
    pagination_class = None

    def get_queryset(self):
        from django.db.models import Count, Q
        return Category.objects.active().prefetch_related("children__children").annotate(
            annotated_product_count=Count(
                "products", filter=Q(products__is_active=True, products__status="active"), distinct=True))

    def list(self, request, *args, **kwargs):
        data = self.get_serializer(self.filter_queryset(self.get_queryset()), many=True).data
        return Response({"status": "success", "data": data})

    def retrieve(self, request, *args, **kwargs):
        category = get_object_or_404(self.get_queryset(), slug=kwargs["slug"])
        return Response({
            "status": "success",
            "data": self.get_serializer(category).data,
            "seo": category.effective_seo(),
            "breadcrumb": category.breadcrumb,
        })


class StaffCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.CATEGORIES_MANAGE
    serializer_class = CategoryStaffSerializer
    queryset = Category.objects.select_related("parent").all()
    http_method_names = ["get", "post", "patch", "put", "delete"]
    filterset_fields = ["parent", "is_active"]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "display_order", "created_at"]
    ordering = ["parent__display_order", "display_order", "name"]

    def get_queryset(self):
        from django.db.models import Count
        qs = super().get_queryset().annotate(direct_product_count=Count("products", distinct=True))
        level = self.request.query_params.get("level")
        if level == "top":
            qs = qs.filter(parent__isnull=True)
        elif level == "sub":
            qs = qs.filter(parent__isnull=False)
        return qs

    def perform_create(self, serializer):
        category = serializer.save()
        AuditService.log(self.request.user, "category.create", "Category", category.pk, {"slug": category.slug}, request=self.request)

    def perform_update(self, serializer):
        category = serializer.save()
        AuditService.log(self.request.user, "category.update", "Category", category.pk, {"slug": category.slug}, request=self.request)

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        CategoryService.safe_delete(category)
        AuditService.log(request.user, "category.delete", "Category", category.pk, {"slug": category.slug}, request=request)
        return Response({"status": "success", "message": "Category deleted."})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        category = self.get_object()
        count = CategoryService.deactivate_tree(category)
        AuditService.log(request.user, "category.deactivate", "Category", category.pk, {"tree_size": count}, request=request)
        return Response({"status": "success", "message": f"Deactivated {count} category(ies)."})

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        category = self.get_object()
        if category.parent and not category.parent.is_active:
            raise ServiceError("Activate the parent category first.", code="parent_inactive")
        category.is_active = True
        category.save(update_fields=["is_active"])
        AuditService.log(request.user, "category.activate", "Category", category.pk, {}, request=request)
        return Response({"status": "success", "message": "Category activated."})

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        pairs = request.data.get("items", [])
        if not isinstance(pairs, list) or not all(isinstance(i, dict) and "id" in i and "display_order" in i for i in pairs):
            raise ServiceError('Expected {"items": [{"id": 1, "display_order": 0}, ...]}', code="invalid_payload")
        CategoryService.reorder(pairs)
        AuditService.log(request.user, "category.reorder", "Category", "", {"count": len(pairs)}, request=request)
        return Response({"status": "success", "message": "Category order updated."})
