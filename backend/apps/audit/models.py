"""Immutable audit trail for every sensitive platform action."""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import UUIDModel


class AuditLog(UUIDModel):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        LOGIN_FAILED = "login_failed", "Login failed"
        PAYMENT_INITIATED = "payment_initiated", "Payment initiated"
        PAYMENT_VERIFIED = "payment_verified", "Payment verified"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        WEBHOOK_RECEIVED = "webhook_received", "Webhook received"
        WEBHOOK_REJECTED = "webhook_rejected", "Webhook rejected"
        REFUND_REQUESTED = "refund_requested", "Refund requested"
        REFUND_APPROVED = "refund_approved", "Refund approved"
        REFUND_COMPLETED = "refund_completed", "Refund completed"
        REFUND_FAILED = "refund_failed", "Refund failed"
        STOCK_ADJUSTED = "stock_adjusted", "Stock adjusted"
        ORDER_STATE_CHANGED = "order_state_changed", "Order state changed"
        PRICE_CHANGED = "price_changed", "Price changed"
        PERMISSION_CHANGED = "permission_changed", "Permission changed"
        SETTINGS_CHANGED = "settings_changed", "Settings changed"
        EXPORT = "export", "Data export"
        OTHER = "other", "Other"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor_email = models.CharField(max_length=254, blank=True)
    actor_role = models.CharField(max_length=80, blank=True)
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=64, blank=True, db_index=True)
    summary = models.CharField(max_length=255, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]
        verbose_name = "Audit log entry"
        verbose_name_plural = "Audit log entries"
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}:{self.entity_id}"

    def save(self, *a, **kw):
        """Audit rows are append-only: updates are rejected at the model layer."""
        if not self._state.adding:
            raise PermissionError("Audit log entries are immutable.")
        return super().save(*a, **kw)

    def delete(self, *a, **kw):
        raise PermissionError("Audit log entries cannot be deleted.")
