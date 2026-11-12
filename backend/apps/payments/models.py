"""
Payment records and raw webhook events.

Two rules govern this module (Section 12 / Section 45 rules 10–12):

1. A payment row only reaches ``success`` after an independent server-side
   verification with Paystack — never because a browser said so.
2. Every webhook delivery is stored with a unique event key before it is
   processed, so retries are idempotent and replay attacks are visible.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Payment(BaseModel):
    class Provider(models.TextChoices):
        PAYSTACK = "paystack", "Paystack"

    class Status(models.TextChoices):
        INITIALIZED = "initialized", "Initialized"
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Abandoned"
        REVERSED = "reversed", "Reversed"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.PAYSTACK)
    reference = models.CharField(
        max_length=100, unique=True, db_index=True,
        help_text="Our reference sent to Paystack. Unique per payment attempt.",
    )
    provider_reference = models.CharField(max_length=120, blank=True, db_index=True)
    access_code = models.CharField(max_length=120, blank=True)

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    amount_kobo = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="NGN")
    amount_verified = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.INITIALIZED, db_index=True
    )
    is_verified = models.BooleanField(
        default=False, help_text="Set only by a successful server-side verification."
    )
    channel = models.CharField(max_length=40, blank=True)
    gateway_response = models.CharField(max_length=255, blank=True)
    authorization = models.JSONField(null=True, blank=True)
    customer_payload = models.JSONField(null=True, blank=True)

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payments",
    )
    initiator_ip = models.GenericIPAddressField(null=True, blank=True)

    provider_created_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    raw_initialize_response = models.JSONField(null=True, blank=True)
    raw_verify_response = models.JSONField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "payments_payment"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "status"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["provider_reference"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gte=0), name="payment_amount_non_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"

    @property
    def is_successful(self) -> bool:
        return self.status == self.Status.SUCCESS and self.is_verified

    @property
    def already_settled(self) -> bool:
        return self.status in {
            self.Status.SUCCESS, self.Status.PARTIALLY_REFUNDED, self.Status.REFUNDED,
        }


class PaymentWebhookEvent(BaseModel):
    """
    One row per Paystack webhook delivery attempt.

    ``event_key`` is ``provider:event_type:transaction_id`` and is unique, which
    makes duplicate deliveries safe and keeps a permanent record of every
    webhook the platform received.
    """

    class ProcessingStatus(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        DUPLICATE = "duplicate", "Duplicate (ignored)"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    provider = models.CharField(max_length=20, default="paystack")
    event_key = models.CharField(max_length=200, unique=True, db_index=True)
    event_type = models.CharField(max_length=80, db_index=True)
    transaction_reference = models.CharField(max_length=120, blank=True, db_index=True)
    payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="webhook_events"
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="webhook_events",
    )
    payload = models.JSONField()
    signature = models.CharField(max_length=255, blank=True)
    signature_valid = models.BooleanField(default=False)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    processing_status = models.CharField(
        max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.RECEIVED,
        db_index=True,
    )
    processing_note = models.CharField(max_length=255, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_webhook_event"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "-created_at"]),
            models.Index(fields=["processing_status"]),
        ]
        verbose_name = "Payment webhook event"

    def __str__(self) -> str:
        return f"{self.event_type} [{self.processing_status}]"

    def mark(self, status: str, note: str = "") -> None:
        self.processing_status = status
        self.processing_note = note[:255]
        self.processed_at = timezone.now()
        self.save(update_fields=["processing_status", "processing_note", "processed_at", "updated_at"])
