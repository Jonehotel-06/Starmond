from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class ReviewQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(moderation_status=Review.ModerationStatus.APPROVED)


class Review(TimeStampedModel):
    class ModerationStatus(models.TextChoices):
        PENDING = "pending", "Pending moderation"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="reviews")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=150, blank=True)
    body = models.TextField(max_length=4000)
    is_verified_purchase = models.BooleanField(default=False)
    moderation_status = models.CharField(max_length=10, choices=ModerationStatus.choices,
                                         default=ModerationStatus.PENDING, db_index=True)
    moderator_note = models.CharField(max_length=255, blank=True)
    moderated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="moderated_reviews")

    objects = ReviewQuerySet.as_manager()

    class Meta:
        db_table = "reviews_review"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(rating__gte=1) & models.Q(rating__lte=5), name="rating_range"),
            models.UniqueConstraint(fields=["product", "customer"], name="one_review_per_product_per_customer",
                                      condition=models.Q(customer__isnull=False)),
        ]
        indexes = [models.Index(fields=["product", "moderation_status"])]

    def __str__(self):
        return f"{self.product.sku}:{self.rating}*"
