from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.references import refund_reference


class Refund(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        PROCESSING = "processing", "Processing at provider"
        SUCCESSFUL = "successful", "Refunded"
        FAILED = "failed", "Failed"
        REJECTED = "rejected", "Rejected"

    reference = models.CharField(max_length=40, unique=True, default=refund_reference, db_index=True)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey("payments.Payment", on_delete=models.PROTECT, related_name="refunds")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="refund_requests")
    requester_email = models.EmailField(blank=True)
    reason = models.TextField()
    requested_amount = models.DecimalField(max_digits=14, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    restock_items = models.BooleanField(default=False, help_text="Restore inventory when the refund completes.")
    provider_refund_id = models.CharField(max_length=80, blank=True)
    provider_response = models.JSONField(default=dict, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="refunds_processed")
    decided_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    staff_notes = models.TextField(blank=True)

    class Meta:
        db_table = "refunds_refund"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(requested_amount__gt=0), name="refund_requested_positive"),
        ]

    def __str__(self):
        return f"{self.reference}:{self.status}"
