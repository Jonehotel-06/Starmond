"""Staff product management: CRUD, publication, variations and images."""
from __future__ import annotations

from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.categories.models import Category
from apps.core.exceptions import NotFound, ValidationError
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsStaff, RequiresPermission
from apps.core.views import BaseAPIView
from apps.products.models import Product, ProductVariation
from apps.products.serializers import ProductDetailSerializer, ProductListSerializer
from apps.products.services import ProductService


class StaffProductView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("products.add_product")]

    def get(self, request):
        queryset = Product.all_objects.select_related("category").order_by("-created_at")
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        if request.query_params.get("q"):
            term = request.query_params["q"]
            queryset = queryset.filter(name__icontains=term) | queryset.filter(sku__icontains=term)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([
            {
                **ProductListSerializer(row).data,
                "status": row.status,
                "deleted_at": row.deleted_at,
                "cost_price": str(row.cost_price) if row.cost_price else None,
            }
            for row in page
        ])

    def post(self, request):
        category = Category.objects.filter(pk=request.data.get("category_id")).first()
        if category is None:
            raise NotFound("Category not found.")
        product = ProductService.create_product(
            name=request.data.get("name", ""),
            category=category,
            price=request.data.get("price"),
            sku=request.data.get("sku", ""),
            actor=request.user,
            opening_stock=int(request.data.get("opening_stock", 0) or 0),
            **{
                key: request.data[key] for key in (
                    "short_description", "description", "specifications", "key_features",
                    "tags", "search_keywords", "compare_at_price", "cost_price",
                    "product_type", "condition", "custom_order_enabled",
                    "custom_order_instructions", "is_featured", "weight_kg",
                    "requires_shipping", "is_heavy", "warranty", "meta_title",
                    "meta_description", "meta_keywords", "status",
                ) if key in request.data
            },
        )
        return self.created(ProductDetailSerializer(product).data, message="Product created.")


class StaffProductDetailView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("products.change_product")]

    def get(self, request, product_id: str):
        product = Product.all_objects.filter(pk=product_id).first()
        if product is None:
            raise NotFound("Product not found.")
        payload = ProductDetailSerializer(product).data
        payload["cost_price"] = str(product.cost_price) if product.cost_price else None
        payload["status"] = product.status
        return self.ok(payload)

    def patch(self, request, product_id: str):
        product = Product.all_objects.filter(pk=product_id).first()
        if product is None:
            raise NotFound("Product not found.")
        fields = dict(request.data)
        if "category_id" in fields:
            category = Category.objects.filter(pk=fields.pop("category_id")).first()
            if category is None:
                raise NotFound("Category not found.")
            fields["category"] = category
        product = ProductService.update_product(product, actor=request.user, **fields)
        return self.ok(ProductDetailSerializer(product).data, message="Product updated.")

    def delete(self, request, product_id: str):
        product = Product.all_objects.filter(pk=product_id).first()
        if product is None:
            raise NotFound("Product not found.")
        ProductService.delete_product(product, actor=request.user)
        return self.ok(message="Product removed from the catalogue.")


class StaffProductPublishView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("products.change_product")]

    def post(self, request, product_id: str, action: str):
        product = Product.all_objects.filter(pk=product_id).first()
        if product is None:
            raise NotFound("Product not found.")
        if action == "publish":
            product = ProductService.publish(product, actor=request.user)
        elif action == "unpublish":
            product = ProductService.unpublish(product, actor=request.user)
        else:
            raise ValidationError("Action must be 'publish' or 'unpublish'.")
        return self.ok({"status": product.status}, message=f"Product {action}ed.")


class StaffVariationView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("products.add_productvariation")]

    def post(self, request, product_id: str):
        product = Product.all_objects.filter(pk=product_id).first()
        if product is None:
            raise NotFound("Product not found.")
        variation = ProductService.add_variation(
            product=product,
            sku=request.data.get("sku", ""),
            attribute_value_ids=request.data.get("attribute_value_ids", []),
            price_override=request.data.get("price_override"),
            compare_at_price=request.data.get("compare_at_price"),
            opening_stock=int(request.data.get("opening_stock", 0) or 0),
            actor=request.user,
        )
        return self.created(
            {"id": str(variation.pk), "sku": variation.sku, "label": variation.label,
             "price": str(variation.effective_price)},
            message="Variation added.",
        )

    def patch(self, request, product_id: str, variation_id: str):
        variation = ProductVariation.objects.filter(
            pk=variation_id, product_id=product_id
        ).first()
        if variation is None:
            raise NotFound("Variation not found.")
        from apps.core.permissions import enforce

        enforce(request.user, "products.change_productvariation")
        variation = ProductService.update_variation(
            variation, actor=request.user,
            **{k: v for k, v in request.data.items()
               if k in {"price_override", "compare_at_price", "position", "is_active", "weight_kg"}},
        )
        return self.ok({"id": str(variation.pk), "sku": variation.sku,
                        "price": str(variation.effective_price)}, message="Variation updated.")


class StaffProductImageView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("products.add_productimage")]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, product_id: str):
        product = Product.all_objects.filter(pk=product_id).first()
        if product is None:
            raise NotFound("Product not found.")
        upload = request.FILES.get("image")
        if upload is None:
            raise ValidationError("An image file is required.")
        record = ProductService.add_image(
            product=product,
            image=upload,
            alt_text=request.data.get("alt_text", ""),
            is_primary=str(request.data.get("is_primary", "")).lower() in {"1", "true", "yes"},
        )
        return self.created(
            {"id": str(record.pk), "url": record.image.url, "is_primary": record.is_primary},
            message="Image uploaded.",
        )
