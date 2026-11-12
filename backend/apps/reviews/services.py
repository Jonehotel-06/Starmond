"""
ReviewService — moderated, verified, non-duplicable reviews.

Rules enforced here:
* one review per customer per product (database constraint + service check);
* the verified-purchase badge comes from a real paid order containing the item;
* nothing appears publicly until a moderator approves it;
* a review may only be edited by its author, inside the edit window.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import (
    ConflictError,
    NotFound,
    PermissionDeniedError,
    ValidationError,
)
from apps.orders.models import Order, OrderItem
from apps.products.models import Product
from apps.reviews.models import Review, ReviewHelpfulVote

logger = logging.getLogger("apps.reviews")


class ReviewService:
    @staticmethod
    def verified_purchase(user, product) -> OrderItem | None:
        """
        Returns the customer's paid order line for this product, if any.

        This is the *only* source of the verified-purchase flag.
        """
        if not getattr(user, "pk", None):
            return None
        return (
            OrderItem.objects.select_related("order")
            .filter(
                product=product,
                order__customer=user,
                order__payment_status__in=[
                    Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED,
                ],
            )
            .order_by("-order__paid_at")
            .first()
        )

    @staticmethod
    @transaction.atomic
    def create_review(
        *,
        user,
        product: Product,
        rating,
        comment: str,
        title: str = "",
        order_item_id: str | None = None,
    ) -> Review:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            raise ValidationError({"rating": ["Rating must be a whole number from 1 to 5."]})
        if rating < 1 or rating > 5:
            raise ValidationError({"rating": ["Rating must be between 1 and 5."]})

        comment = (comment or "").strip()
        if len(comment) < 10:
            raise ValidationError({"comment": ["Please write at least 10 characters."]})
        if len(comment) > 4000:
            raise ValidationError({"comment": ["Reviews are limited to 4000 characters."]})

        if Review.objects.filter(product=product, user=user).exists():
            raise ConflictError("You have already reviewed this product.")

        purchase = ReviewService.verified_purchase(user, product)
        order_item = None
        if purchase is not None:
            order_item = purchase
        elif order_item_id:
            candidate = OrderItem.objects.filter(
                pk=order_item_id, product=product, order__customer=user
            ).first()
            if candidate is not None and candidate.order.is_paid:
                order_item = candidate

        review = Review.objects.create(
            product=product,
            user=user,
            order_item=order_item,
            rating=rating,
            title=(title or "")[:150],
            comment=comment,
            is_verified_purchase=order_item is not None,
            moderation_status=Review.ModerationStatus.PENDING,
            is_approved=False,
        )
        logger.info("Review %s submitted for product %s (pending moderation)", review.pk, product.pk)
        return review

    @staticmethod
    @transaction.atomic
    def update_review(review: Review, *, user, rating=None, comment=None, title=None) -> Review:
        if review.user_id != user.pk:
            raise PermissionDeniedError("You can only edit your own review.")
        age_days = (timezone.now() - review.created_at).days
        if age_days > settings.REVIEW_EDIT_WINDOW_DAYS:
            raise ConflictError(
                f"Reviews can only be edited within {settings.REVIEW_EDIT_WINDOW_DAYS} days."
            )
        if rating is not None:
            try:
                rating = int(rating)
            except (TypeError, ValueError):
                raise ValidationError({"rating": ["Rating must be a whole number from 1 to 5."]})
            if not 1 <= rating <= 5:
                raise ValidationError({"rating": ["Rating must be between 1 and 5."]})
            review.rating = rating
        if comment is not None:
            comment = comment.strip()
            if len(comment) < 10:
                raise ValidationError({"comment": ["Please write at least 10 characters."]})
            review.comment = comment[:4000]
        if title is not None:
            review.title = title[:150]

        # An edited review returns to moderation — this is deliberate.
        review.is_approved = False
        review.moderation_status = Review.ModerationStatus.PENDING
        review.save()
        review.product.refresh_rating()
        return review

    @staticmethod
    @transaction.atomic
    def moderate(review: Review, *, approved: bool, moderator, note: str = "") -> Review:
        review.is_approved = bool(approved)
        review.moderation_status = (
            Review.ModerationStatus.APPROVED if approved else Review.ModerationStatus.REJECTED
        )
        review.moderation_note = (note or "")[:255]
        review.moderated_by = moderator if getattr(moderator, "pk", None) else None
        review.moderated_at = timezone.now()
        review.save()
        review.product.refresh_rating()
        return review

    @staticmethod
    def reply(review: Review, *, reply_text: str, staff) -> Review:
        review.staff_reply = (reply_text or "").strip()[:4000]
        review.replied_at = timezone.now()
        review.save(update_fields=["staff_reply", "replied_at", "updated_at"])
        return review

    @staticmethod
    @transaction.atomic
    def mark_helpful(review: Review, user) -> int:
        if review.user_id == user.pk:
            raise ValidationError("You cannot mark your own review as helpful.")
        _, created = ReviewHelpfulVote.objects.get_or_create(review=review, user=user)
        if not created:
            return review.helpful_count
        Review.objects.filter(pk=review.pk).update(helpful_count=models_f() + 1)
        review.refresh_from_db(fields=["helpful_count"])
        return review.helpful_count

    @staticmethod
    def get_review(review_id: str) -> Review:
        review = Review.objects.select_related("product", "user").filter(pk=review_id).first()
        if review is None:
            raise NotFound("Review not found.")
        return review

    @staticmethod
    def product_rating_summary(product: Product) -> dict:
        from django.db.models import Count

        distribution = {
            row["rating"]: row["total"]
            for row in product.reviews.filter(is_approved=True)
            .values("rating")
            .annotate(total=Count("id"))
        }
        return {
            "average": float(product.rating_average or 0),
            "count": product.rating_count,
            "distribution": {str(star): distribution.get(star, 0) for star in range(5, 0, -1)},
        }


def models_f():
    from django.db.models import F

    return F("helpful_count")
