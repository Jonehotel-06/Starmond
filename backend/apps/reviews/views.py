"""Reviews: public listing, authenticated submission, staff moderation."""
from __future__ import annotations

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.core.exceptions import NotFound
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import RequiresPermission
from apps.core.views import BaseAPIView
from apps.products.models import Product
from apps.reviews.models import Review
from apps.reviews.serializers import ReviewCreateSerializer, ReviewSerializer
from apps.reviews.services import ReviewService


class ProductReviewsView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request, slug: str):
        product = Product.objects.public().filter(slug=slug).first()
        if product is None:
            raise NotFound("Product not found.")
        queryset = product.reviews.filter(is_approved=True).select_related("user").order_by(
            "-is_verified_purchase", "-created_at"
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(
            ReviewSerializer(page, many=True, context={"request": request}).data
        )
        response.data["summary"] = ReviewService.product_rating_summary(product)
        return response


class ReviewCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "review"

    def post(self, request):
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        product = Product.objects.public().filter(pk=data["product_id"]).first()
        if product is None:
            raise NotFound("Product not found.")
        review = ReviewService.create_review(
            user=request.user,
            product=product,
            rating=data["rating"],
            comment=data["comment"],
            title=data.get("title", ""),
            order_item_id=str(data["order_item_id"]) if data.get("order_item_id") else None,
        )
        return self.created(
            ReviewSerializer(review, context={"request": request}).data,
            message="Thank you. Your review will appear once it has been moderated.",
        )


class ReviewUpdateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, review_id: str):
        review = ReviewService.get_review(review_id)
        updated = ReviewService.update_review(
            review, user=request.user,
            rating=request.data.get("rating"),
            comment=request.data.get("comment"),
            title=request.data.get("title"),
        )
        return self.ok(ReviewSerializer(updated, context={"request": request}).data,
                       message="Review updated and resubmitted for moderation.")


class ReviewHelpfulView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "review"

    def post(self, request, review_id: str):
        review = ReviewService.get_review(review_id)
        count = ReviewService.mark_helpful(review, request.user)
        return self.ok({"helpful_count": count}, message="Thanks for your feedback.")


class MyReviewsView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Review.objects.filter(user=request.user).select_related("product")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            ReviewSerializer(page, many=True, context={"request": request}).data
        )


class StaffReviewModerationView(BaseAPIView):
    permission_classes = [RequiresPermission.of("reviews.change_review")]

    def get(self, request):
        queryset = Review.objects.select_related("product", "user").order_by("-created_at")
        if request.query_params.get("status"):
            queryset = queryset.filter(moderation_status=request.query_params["status"])
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            ReviewSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request, review_id: str):
        review = ReviewService.get_review(review_id)
        action = request.data.get("action", "approve")
        if action == "reply":
            updated = ReviewService.reply(
                review, reply_text=request.data.get("reply", ""), staff=request.user
            )
            return self.ok(ReviewSerializer(updated, context={"request": request}).data,
                           message="Reply published.")
        updated = ReviewService.moderate(
            review, approved=(action == "approve"), moderator=request.user,
            note=request.data.get("note", ""),
        )
        return self.ok(ReviewSerializer(updated, context={"request": request}).data,
                       message=f"Review {action}d.")
