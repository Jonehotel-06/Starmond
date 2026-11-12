"""
Product reviews with moderation and verified-purchase badges.

The "verified purchase" flag is derived from real order records, never from a
client-supplied boolean (Section 17).
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Review(BaseModel):
    class ModerationStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    order_item = models.ForeignKey(
        "orders.OrderItem", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=150, blank=True)
    comment = models.TextField(max_length=4000)
    is_verified_purchase = models.BooleanField(default=False, editable=False)
    is_approved = models.BooleanField(default=False, db_index=True)
    moderation_status = models.CharField(
        max_length=20, choices=ModerationStatus.choices, default=ModerationStatus.PENDING,
        db_index=True,
    )
    moderation_note = models.CharField(max_length=255, blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviews_moderated",
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    helpful_count = models.PositiveIntegerField(default=0)
    is_flagged = models.BooleanField(default=False)
    staff_reply = models.TextField(blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reviews_review"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="uniq_review_per_customer"),
        ]
        indexes = [
            models.Index(fields=["product", "is_approved", "-created_at"]),
            models.Index(fields=["moderation_status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.rating}★ {self.product_id} by {self.user_id}"

    @property
    def reviewer_name(self) -> str:
        name = self.user.display_name if self.user_id else "Customer"
        parts = name.split()
        if len(parts) > 1:
            return f"{parts[0]} {parts[-1][0]}."
        return name


class ReviewHelpfulVote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="helpful_votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_votes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reviews_helpful_vote"
        constraints = [models.UniqueConstraint(fields=["review", "user"], name="uniq_review_vote")]
