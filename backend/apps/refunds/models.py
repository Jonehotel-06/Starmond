"""
Refund records.

A refund moves through: requested → under review → approved → processing →
completed | failed. ``completed`` is only ever set after the provider confirms
the money has actually been returned (Section 33).
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Refund(BaseModel):
    class Type(models.TextChoices):
        FULL = "full", "Full refund"
        PARTIAL = "partial", "Partial refund"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PROCESSING = "processing", "Processing with provider"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Reason(models.TextChoices):
        DAMAGED = "damaged", "Item arrived damaged"
        WRONG_ITEM = "wrong_item", "Wrong item delivered"
        NOT_AS_DESCRIBED = "not_as_described", "Not as described"
        CHANGED_MIND = "changed_mind", "Changed my mind"
        LATE_DELIVERY = "late_delivery", "Delivery was too late"
        DUPLICATE_CHARGE = "duplicate_charge", "Duplicate charge"
        OTHER = "other", "Other"

    refund_number = models.CharField(max_length=32, unique=True, db_index=True, editable=False)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey(
        "payments.Payment", null=True, blank=True, on_delete=models.PROTECT,
        related_name="refunds",
    )

    refund_type = models.CharField(max_length=20, choices=Type.choices, default=Type.PARTIAL)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True
    )
    reason_category = models.CharField(max_length=30, choices=Reason.choices, default=Reason.OTHER)
    customer_note = models.TextField(blank=True)
    internal_note = models.TextField(blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    amount_requested = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(0)]
    )
    amount_approved = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    amount_refunded = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="NGN")

    provider = models.CharField(max_length=20, default="paystack")
    provider_refund_id = models.CharField(max_length=120, blank=True, db_index=True)
    provider_status = models.CharField(max_length=60, blank=True)
    provider_response = models.JSONField(null=True, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)

    restock_items = models.BooleanField(default=False)
    restock_processed = models.BooleanField(default=False)
    restocked_at = models.DateTimeField(null=True, blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="refund_requests",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="refunds_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "refunds_refund"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["order"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount_refunded__gte=0), name="refund_amount_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.refund_number} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in {
            self.Status.REQUESTED, self.Status.UNDER_REVIEW, self.Status.APPROVED,
            self.Status.PROCESSING,
        }

    @property
    def is_completed(self) -> bool:
        return self.status == self.Status.COMPLETED

    def save(self, *a, **kw):
        if not self.refund_number:
            self.refund_number = Refund.generate_number()
        super().save(*a, **kw)

    @staticmethod
    def generate_number() -> str:
        from django.utils import timezone

        stamp = timezone.now().strftime("%y%m%d")
        for _ in range(20):
            candidate = f"RFN-{stamp}-{uuid.uuid4().hex[:6].upper()}"
            if not Refund.objects.filter(refund_number=candidate).exists():
                return candidate
        raise RuntimeError("Unable to allocate a refund number.")


class RefundItem(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name="items")
    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.PROTECT, related_name="refund_items")
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "refunds_item"
        constraints = [
            models.UniqueConstraint(fields=["refund", "order_item"], name="uniq_refund_order_item"),
            models.CheckConstraint(check=models.Q(quantity__gte=1), name="refund_item_quantity_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.order_item_id} x{self.quantity}"
