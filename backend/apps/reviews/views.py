import django_filters as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission
from apps.products.models import Product

from .models import Review
from .serializers import ReviewCreateSerializer, ReviewPublicSerializer, ReviewStaffSerializer
from .services import ReviewService


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(tags=["reviews"], responses=OpenApiTypes.OBJECT)
class ProductReviewListView(viewsets.ViewSet):
    """GET /api/reviews/product/<slug>/ — approved reviews + summary."""
    permission_classes = [AllowAny]

    def list(self, request, product_slug=None):
        product = Product.objects.filter(slug=product_slug, status=Product.Status.ACTIVE, is_active=True).first()
        if not product:
            raise ServiceError("Product not found.", code="not_found", status_code=404)
        reviews = product.reviews.approved()[:100]
        from apps.core.pagination import StandardPagination
        paginator = StandardPagination()
        page = paginator.paginate_queryset(list(reviews), request, view=self)
        response = paginator.get_paginated_response(ReviewPublicSerializer(page, many=True).data)
        response.data["summary"] = ReviewService.product_summary(product)
        return response


@extend_schema(tags=["reviews"], request=ReviewCreateSerializer, responses={201: OpenApiTypes.OBJECT})
class CustomerReviewCreateView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def create(self, request):
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = ReviewService.create_review(
            customer=request.user, product=serializer.validated_data["product"],
            rating=serializer.validated_data["rating"], title=serializer.validated_data.get("title", ""),
            body=serializer.validated_data["body"])
        return Response({"status": "success", "message": "Review submitted and awaiting moderation.",
                         "data": ReviewPublicSerializer(review).data}, status=status.HTTP_201_CREATED)


class StaffReviewFilter(filters.FilterSet):
    class Meta:
        model = Review
        fields = ["moderation_status", "product", "is_verified_purchase"]


class StaffReviewViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.REVIEWS_MODERATE
    serializer_class = ReviewStaffSerializer
    queryset = Review.objects.select_related("product", "customer", "order").all()
    filterset_class = StaffReviewFilter
    search_fields = ["title", "body", "product__name"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        review = ReviewService.moderate(self.get_object(), Review.ModerationStatus.APPROVED, request.user,
                                        note=request.data.get("note", ""))
        AuditService.log(request.user, "review.approve", "Review", review.pk, {}, request=request)
        return Response({"status": "success", "data": self.get_serializer(review).data})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        review = ReviewService.moderate(self.get_object(), Review.ModerationStatus.REJECTED, request.user,
                                        note=request.data.get("note", ""))
        AuditService.log(request.user, "review.reject", "Review", review.pk, {}, request=request)
        return Response({"status": "success", "data": self.get_serializer(review).data})
