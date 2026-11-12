"""Staff category management (Section 20/21)."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated

from apps.categories.models import Category
from apps.categories.serializers import CategoryDetailSerializer, CategoryListSerializer
from apps.categories.services import CategoryService
from apps.core.exceptions import NotFound
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsStaff, RequiresPermission
from apps.core.views import BaseAPIView


class StaffCategoryView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("categories.add_category")]

    def get(self, request):
        queryset = Category.all_objects.select_related("parent").order_by("depth", "position", "name")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([
            {
                **CategoryListSerializer(row).data,
                "status": row.status,
                "is_active": row.is_active,
                "parent_id": str(row.parent_id) if row.parent_id else None,
                "deleted_at": row.deleted_at,
            }
            for row in page
        ])

    def post(self, request):
        parent = None
        if request.data.get("parent_id"):
            parent = Category.objects.filter(pk=request.data["parent_id"]).first()
            if parent is None:
                raise NotFound("Parent category not found.")
        category = CategoryService.create(
            name=request.data.get("name", ""),
            parent=parent,
            description=request.data.get("description", ""),
            short_description=request.data.get("short_description", ""),
            status=request.data.get("status", "draft"),
            is_featured=bool(request.data.get("is_featured")),
            position=int(request.data.get("position", 0) or 0),
            meta_title=request.data.get("meta_title", ""),
            meta_description=request.data.get("meta_description", ""),
            icon=request.data.get("icon", ""),
        )
        return self.created(CategoryDetailSerializer(category).data, message="Category created.")


class StaffCategoryDetailView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("categories.change_category")]

    def patch(self, request, category_id: str):
        category = Category.objects.filter(pk=category_id).first()
        if category is None:
            raise NotFound("Category not found.")
        fields = {k: v for k, v in request.data.items() if k != "parent_id"}
        if "parent_id" in request.data:
            fields["parent"] = (
                Category.objects.filter(pk=request.data["parent_id"]).first()
                if request.data["parent_id"] else None
            )
        category = CategoryService.update(category, **fields)
        return self.ok(CategoryDetailSerializer(category).data, message="Category updated.")

    def delete(self, request, category_id: str):
        category = Category.objects.filter(pk=category_id).first()
        if category is None:
            raise NotFound("Category not found.")
        CategoryService.delete(category)
        return self.ok(message="Category deleted.")
