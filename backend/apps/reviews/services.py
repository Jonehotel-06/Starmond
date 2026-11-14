from django.db import transaction

from apps.core.exceptions import ServiceError


class ReviewService:
    @staticmethod
    def verify_purchase(customer, product):
        """Derived strictly from actual paid/delivered order records."""
        from apps.orders.models import Order, OrderItem
        return OrderItem.objects.filter(
            order__customer=customer, product=product,
            order__payment_status__in=["paid", "partially_refunded", "refunded"],
        ).select_related("order").first()

    @classmethod
    @transaction.atomic
    def create_review(cls, *, customer, product, rating, title, body):
        from .models import Review
        if not product.is_public:
            raise ServiceError("This product is not available for review.", code="product_unavailable")
        if Review.objects.filter(product=product, customer=customer).exists():
            raise ServiceError("You have already reviewed this product.", code="duplicate_review", status_code=409)
        order_item = cls.verify_purchase(customer, product)
        review = Review.objects.create(
            product=product, customer=customer,
            order=order_item.order if order_item else None,
            rating=rating, title=title[:150], body=body[:4000],
            is_verified_purchase=bool(order_item),
        )
        return review

    @staticmethod
    @transaction.atomic
    def moderate(review, status, moderator, note=""):
        from .models import Review
        if status not in (Review.ModerationStatus.APPROVED, Review.ModerationStatus.REJECTED):
            raise ServiceError("Moderation status must be approved or rejected.", code="invalid_status")
        review.moderation_status = status
        review.moderated_by = moderator
        review.moderator_note = note[:255]
        review.save(update_fields=["moderation_status", "moderated_by", "moderator_note", "updated_at"])
        return review

    @staticmethod
    def product_summary(product):
        from django.db.models import Avg, Count
        stats = product.reviews.approved().aggregate(avg=Avg("rating"), count=Count("id"))
        return {
            "average_rating": round(float(stats["avg"]), 2) if stats["avg"] else None,
            "review_count": stats["count"] or 0,
        }
