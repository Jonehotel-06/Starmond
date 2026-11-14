from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    class Kind(models.TextChoices):
        ORDER = "order", "Order update"
        PAYMENT = "payment", "Payment update"
        REFUND = "refund", "Refund update"
        ACCOUNT = "account", "Account"
        PROMOTION = "promotion", "Promotion"
        SYSTEM = "system", "System"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=180)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    dedupe_key = models.CharField(max_length=160, unique=True, null=True, blank=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at"]


class NewsletterSubscriber(TimeStampedModel):
    email = models.EmailField(unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=60, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_newsletter"
        ordering = ["-created_at"]


class Enquiry(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField(max_length=4000)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries")
    response_note = models.TextField(blank=True)
    related_order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries")

    class Meta:
        db_table = "notifications_enquiry"
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"
