"""Central media registry so every uploaded asset is traceable and auditable."""
from __future__ import annotations

import os

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models

from apps.core.models import BaseModel


class MediaAsset(BaseModel):
    class Kind(models.TextChoices):
        PRODUCT = "product", "Product"
        CATEGORY = "category", "Category"
        BANNER = "banner", "Banner"
        CONTENT = "content", "Content"
        BRAND = "brand", "Brand"
        OTHER = "other", "Other"

    file = models.FileField(upload_to="media_library/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER, db_index=True)
    mime_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    alt_text = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="media_uploads",
    )
    checksum = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        db_table = "media_asset"
        ordering = ["-created_at"]
        verbose_name = "Media asset"

    def __str__(self) -> str:
        return self.original_name or os.path.basename(self.file.name)

    @property
    def url(self) -> str:
        try:
            return self.file.url
        except ValueError:
            return ""

    def clean(self):
        if self.size_bytes and self.size_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
            raise DjangoValidationError(
                {"file": f"Files must be smaller than "
                         f"{settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."}
            )
