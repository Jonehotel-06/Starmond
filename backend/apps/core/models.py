"""Core model primitives shared by every STARMOND application."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    """
    Primary-key model that never leaks a sequential database id.

    ``id`` is a UUID4 primary key and ``public_id`` remains available as an
    explicit, stable handle for API payloads and signed links.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """UUID primary key + audit timestamps."""

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class SoftDeleteModel(models.Model):
    """
    Soft deletion for records that financial and audit history must retain.

    Rows are never physically removed once they can be referenced by an order,
    payment or refund.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"] if hasattr(self, "updated_at") else ["deleted_at"])

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])


class PublishableQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status="published")

    def public(self):
        return self.published()


class PublishableModel(models.Model):
    """Publication workflow shared by products and CMS content."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    def publish(self, when=None):
        self.status = self.Status.PUBLISHED
        self.published_at = when or timezone.now()
        self.save(update_fields=["status", "published_at", "updated_at"] if hasattr(self, "updated_at") else ["status", "published_at"])


def money_field(**kwargs):
    """Consistent NGN-capable money column."""
    kwargs.setdefault("max_digits", 14)
    kwargs.setdefault("decimal_places", 2)
    return models.DecimalField(**kwargs)


def current_actor():
    """Returns the actor currently bound to the request thread, if any."""
    from apps.core.middleware import get_current_request

    request = get_current_request()
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def actor_display(user) -> str:
    if user is None:
        return "system"
    return getattr(user, "email", None) or str(user)


class CurrencyMixin(models.Model):
    """Records the currency a monetary fact was denominated in."""

    currency = models.CharField(max_length=3, default=settings.DEFAULT_CURRENCY, editable=False)

    class Meta:
        abstract = True


# Imported last: the idempotency infrastructure defines a model that builds on
# ``BaseModel``. Importing here keeps a single authoritative models module for
# the Django app registry without a circular import at module load time.
from apps.core.idempotency import IdempotencyKey  # noqa: E402,F401
