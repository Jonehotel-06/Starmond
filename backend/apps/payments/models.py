from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.references import payment_reference


class Payment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Abandoned"
        REVERSED = "reversed", "Reversed"
        REFUNDED = "refunded", "Refunded"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"

    class Provider(models.TextChoices):
        PAYSTACK = "paystack", "Paystack"

    reference = models.CharField(max_length=40, unique=True, default=payment_reference, db_index=True)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=12, choices=Provider.choices, default=Provider.PAYSTACK)
    provider_reference = models.CharField(max_length=120, unique=True, db_index=True,
                                          help_text="Reference sent to Paystack (unique per attempt).")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    channel = models.CharField(max_length=30, blank=True)
    provider_transaction_id = models.BigIntegerField(null=True, blank=True)
    authorization_url = models.URLField(max_length=500, blank=True)
    access_code = models.CharField(max_length=60, blank=True)
    initialized_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    last_verification_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "payments_payment"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order", "status"]), models.Index(fields=["status", "created_at"])]
        constraints = [models.CheckConstraint(check=models.Q(amount__gt=0), name="payment_amount_positive")]

    def __str__(self):
        return f"{self.reference}:{self.status}"

    @property
    def is_settled(self):
        return self.status in (self.Status.SUCCESSFUL, self.Status.REFUNDED, self.Status.PARTIALLY_REFUNDED)


class PaymentWebhookEvent(models.Model):
    """Every Paystack webhook delivery is stored once (provider_event_id is
    unique) so retries can never double-process a charge."""
    provider_event_id = models.CharField(max_length=120, unique=True, db_index=True)
    event_type = models.CharField(max_length=80, db_index=True)
    payload = models.JSONField(default=dict)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="webhook_events")
    processed = models.BooleanField(default=False)
    outcome = models.CharField(max_length=60, blank=True)
    error = models.CharField(max_length=500, blank=True)
    signature_valid = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_webhook_event"
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.event_type}:{self.provider_event_id}"
