"""
Per-URL SEO overrides and redirects (Section 25).

Products and categories carry their own SEO fields; this model handles the
remaining public URLs (home, search, static pages) plus canonical/robots control.
"""
from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class SEOSetting(BaseModel):
    path = models.CharField(
        max_length=300, unique=True, db_index=True,
        help_text="Absolute path, e.g. '/' or '/shop'. Use '*' for the default template.",
    )
    title = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=320, blank=True)
    keywords = models.CharField(max_length=255, blank=True)
    canonical_url = models.URLField(blank=True)
    og_title = models.CharField(max_length=200, blank=True)
    og_description = models.CharField(max_length=320, blank=True)
    og_image_url = models.URLField(blank=True)
    twitter_card = models.CharField(max_length=40, default="summary_large_image")
    robots = models.CharField(
        max_length=60, default="index,follow",
        help_text="e.g. 'index,follow' or 'noindex,nofollow'.",
    )
    structured_data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "seo_setting"
        ordering = ["path"]

    def __str__(self) -> str:
        return self.path


class Redirect(BaseModel):
    """301/302 redirects so retired URLs never become dead links."""

    class Status(models.IntegerChoices):
        MOVED_PERMANENTLY = 301, "301 Moved permanently"
        FOUND = 302, "302 Found"
        TEMPORARY = 307, "307 Temporary"

    from_path = models.CharField(max_length=300, unique=True, db_index=True)
    to_path = models.CharField(max_length=300)
    status_code = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.MOVED_PERMANENTLY)
    is_active = models.BooleanField(default=True)
    hit_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        db_table = "seo_redirect"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.from_path} → {self.to_path} ({self.status_code})"
