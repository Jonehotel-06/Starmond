"""Outbound email log — every transactional message is recorded."""
from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class EmailLog(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    class Category(models.TextChoices):
        TRANSACTIONAL = "transactional", "Transactional"
        MARKETING = "marketing", "Marketing"
        SECURITY = "security", "Security"
        SYSTEM = "system", "System"

    to_email = models.EmailField(db_index=True)
    to_name = models.CharField(max_length=150, blank=True)
    from_email = models.EmailField(blank=True)
    subject = models.CharField(max_length=255)
    template = models.CharField(max_length=120, db_index=True)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.TRANSACTIONAL, db_index=True
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)

    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="email_logs",
    )
    related_type = models.CharField(max_length=60, blank=True, db_index=True)
    related_id = models.CharField(max_length=64, blank=True, db_index=True)
    context_keys = models.JSONField(default=list, blank=True)

    is_duplicate_suspected = models.BooleanField(default=False)

    class Meta:
        db_table = "emails_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["template", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["related_type", "related_id"]),
        ]
        verbose_name = "Email log"

    def __str__(self) -> str:
        return f"{self.template} → {self.to_email} [{self.status}]"
