"""
Idempotency infrastructure.

Protects order creation, payment initialisation and refund submission against
double submissions, retried requests and client-side double clicks.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import IdempotencyConflict
from apps.core.models import BaseModel
from django.db import models

logger = logging.getLogger("apps.core.idempotency")

IDEMPOTENCY_HEADER = "HTTP_X_IDEMPOTENCY_KEY"


class IdempotencyKey(BaseModel):
    """
    A stored (scope, key) pair with the request fingerprint and the response
    that was produced the first time the request succeeded.
    """

    class State(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    scope = models.CharField(max_length=120, db_index=True)
    key = models.CharField(max_length=255, db_index=True)
    request_fingerprint = models.CharField(max_length=64)
    state = models.CharField(max_length=20, choices=State.choices, default=State.IN_PROGRESS, db_index=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    resource_type = models.CharField(max_length=80, blank=True)
    resource_id = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "core_idempotency_key"
        constraints = [
            models.UniqueConstraint(fields=["scope", "key"], name="uniq_idempotency_scope_key"),
        ]
        indexes = [models.Index(fields=["expires_at"])]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key} ({self.state})"


def lookup_completed(scope: str, key: str | None) -> IdempotencyKey | None:
    """
    Returns the stored response for an already-completed key.

    Checked *before* any state validation so a double submit (e.g. the customer
    clicking Pay twice, or a network retry after the cart was already converted)
    resolves to the original resource instead of an error.
    """
    if not key:
        return None
    return IdempotencyKey.objects.filter(
        scope=scope,
        key=str(key).strip(),
        state=IdempotencyKey.State.COMPLETED,
    ).first()


def fingerprint(payload) -> str:
    """Deterministic hash of a request payload used to detect key reuse."""
    try:
        serialised = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        serialised = str(payload)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


class IdempotentRunner:
    """
    Context manager that guarantees an operation body runs at most once per
    (scope, key) and that a replay returns the original response.
    """

    def __init__(self, scope: str, key: str | None, payload=None, actor=None):
        if not key:
            raise IdempotencyConflict("An X-Idempotency-Key header is required for this endpoint.")
        key = str(key).strip()
        if not (8 <= len(key) <= 255):
            raise IdempotencyConflict("X-Idempotency-Key must be between 8 and 255 characters.")
        self.scope = scope
        self.key = key
        self.payload = payload
        self.actor = actor
        self.record: IdempotencyKey | None = None
        self.replayed = False
        self._replay_body = None
        self._replay_status = None

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self):
        fp = fingerprint(self.payload)
        try:
            with transaction.atomic():
                self.record = IdempotencyKey.objects.create(
                    scope=self.scope,
                    key=self.key,
                    request_fingerprint=fp,
                    state=IdempotencyKey.State.IN_PROGRESS,
                    expires_at=timezone.now()
                    + timedelta(hours=settings.IDEMPOTENCY_KEY_TTL_HOURS),
                )
        except IntegrityError:
            existing = IdempotencyKey.objects.filter(scope=self.scope, key=self.key).first()
            if existing is None:
                raise IdempotencyConflict("Idempotency key could not be reserved. Please retry.")

            if existing.request_fingerprint != fp:
                raise IdempotencyConflict(
                    "This idempotency key was already used with a different request payload."
                )
            if existing.state == IdempotencyKey.State.COMPLETED:
                self.replayed = True
                self.record = existing
                self._replay_body = existing.response_body
                self._replay_status = existing.response_status or 200
                return self
            if existing.state == IdempotencyKey.State.IN_PROGRESS:
                raise IdempotencyConflict(
                    "An identical request is already being processed. Please wait and retry."
                )
            # FAILED → allow a retry by resetting the reservation.
            existing.state = IdempotencyKey.State.IN_PROGRESS
            existing.request_fingerprint = fp
            existing.response_body = None
            existing.response_status = None
            existing.save(update_fields=["state", "request_fingerprint", "response_body", "response_status", "updated_at"])
            self.record = existing
        return self

    def complete(self, status_code: int, body, resource_type: str = "", resource_id: str = "") -> None:
        if self.record is None:
            return
        IdempotencyKey.objects.filter(pk=self.record.pk).update(
            state=IdempotencyKey.State.COMPLETED,
            response_status=status_code,
            response_body=body,
            resource_type=resource_type,
            resource_id=str(resource_id),
            updated_at=timezone.now(),
        )

    def fail(self) -> None:
        if self.record is None:
            return
        IdempotencyKey.objects.filter(pk=self.record.pk).update(
            state=IdempotencyKey.State.FAILED, updated_at=timezone.now()
        )

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None and not self.replayed:
            try:
                self.fail()
            except Exception:  # pragma: no cover - never mask the original error
                logger.exception("Failed to release idempotency reservation")
        return False

    # -- accessors ---------------------------------------------------------
    @property
    def replayed_response(self):
        return self._replay_body, self._replay_status


def purge_expired(now=None) -> int:
    """Housekeeping: delete expired idempotency records."""
    now = now or timezone.now()
    deleted, _ = IdempotencyKey.objects.filter(expires_at__lt=now).delete()
    return deleted
