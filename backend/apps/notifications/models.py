"""In-app notifications and the newsletter/enquiry inbox."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Notification(BaseModel):
    class Type(models.TextChoices):
        ORDER = "order", "Order"
        PAYMENT = "payment", "Payment"
        SHIPPING = "shipping", "Shipping"
        REFUND = "refund", "Refund"
        ACCOUNT = "account", "Account"
        PROMOTION = "promotion", "Promotion"
        SYSTEM = "system", "System"
        REVIEW = "review", "Review"
        STOCK = "stock", "Stock alert"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    title = models.CharField(max_length=180)
    message = models.TextField()
    action_url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=150, blank=True, db_index=True)
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.notification_type}: {self.title}"


class NewsletterSubscriber(BaseModel):
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=60, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_newsletter_subscriber"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.email


class Enquiry(BaseModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=150)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=16, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="enquiries",
    )
    order_number = models.CharField(max_length=32, blank=True, db_index=True)
    staff_response = models.TextField(blank=True)
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="enquiries_answered",
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "notifications_enquiry"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.subject} — {self.email}"
