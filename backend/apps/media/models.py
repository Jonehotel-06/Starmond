"""Media library. Binaries live in object storage (Backblaze B2 in production,
the local filesystem in development); the database stores keys + metadata only."""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class MediaAsset(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        PRODUCT_IMAGE = "product_image", "Product image"
        CATEGORY_IMAGE = "category_image", "Category image"
        BANNER = "banner", "Banner"
        LOGO = "logo", "Logo"
        REFERENCE_IMAGE = "reference_image", "Customer reference image"
        OTHER = "other", "Other"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    class Status(models.TextChoices):
        READY = "ready", "Ready"
        PROCESSING = "processing", "Processing"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.OTHER, db_index=True)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.READY, db_index=True)
    object_key = models.CharField(max_length=500)
    thumbnail_key = models.CharField(max_length=500, blank=True)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField(default=0)
    width = models.PositiveBigIntegerField(null=True, blank=True)
    height = models.PositiveBigIntegerField(null=True, blank=True)
    alt_text = models.CharField(max_length=255, blank=True)
    related_object_type = models.CharField(max_length=80, blank=True)
    related_object_id = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="media_assets")

    class Meta:
        db_table = "media_asset"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["related_object_type", "related_object_id"], name="media_related_idx")]

    def __str__(self):
        return f"{self.original_name} ({self.kind})"
