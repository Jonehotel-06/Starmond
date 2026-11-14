from django.db import models


class EmailLog(models.Model):
    """Delivery log for every transactional email. Email failures never
    invalidate payments/orders — they are recorded here and retried."""
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DUPLICATE_SKIPPED = "duplicate_skipped", "Duplicate skipped"

    recipient = models.EmailField(db_index=True)
    template_key = models.CharField(max_length=60, db_index=True)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=18, choices=Status.choices, default=Status.QUEUED, db_index=True)
    dedupe_key = models.CharField(max_length=160, unique=True, null=True, blank=True, db_index=True)
    related_order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="email_logs")
    related_payment = models.ForeignKey("payments.Payment", on_delete=models.SET_NULL, null=True, blank=True, related_name="email_logs")
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    context_snapshot = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "emails_log"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "attempts"])]

    def __str__(self):
        return f"{self.template_key}->{self.recipient}:{self.status}"
