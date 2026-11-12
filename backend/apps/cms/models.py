"""
Business settings and editable public content (Section 24).

Settings are typed key/value rows so the owner can change store behaviour and
contact details from the dashboard without a deployment.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models

from apps.core.models import BaseModel, PublishableModel
from apps.core.utils import unique_slug


class BusinessSetting(BaseModel):
    class ValueType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Boolean"
        JSON = "json", "JSON"
        EMAIL = "email", "Email"
        URL = "url", "URL"
        MONEY = "money", "Money"

    class Group(models.TextChoices):
        GENERAL = "general", "General"
        CONTACT = "contact", "Contact"
        COMMERCE = "commerce", "Commerce"
        PAYMENT = "payment", "Payment"
        SHIPPING = "shipping", "Shipping"
        EMAIL = "email", "Email"
        SOCIAL = "social", "Social"
        LEGAL = "legal", "Legal"
        SEO = "seo", "SEO"

    key = models.CharField(max_length=100, unique=True, db_index=True)
    label = models.CharField(max_length=150)
    value = models.TextField(blank=True)
    value_type = models.CharField(max_length=20, choices=ValueType.choices, default=ValueType.TEXT)
    group = models.CharField(max_length=20, choices=Group.choices, default=Group.GENERAL, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    is_public = models.BooleanField(
        default=True, help_text="Expose to the public storefront configuration endpoint."
    )
    is_editable = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "cms_business_setting"
        ordering = ["group", "position", "key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.value[:40]}"

    def clean(self):
        if self.value_type == self.ValueType.NUMBER:
            try:
                float(self.value)
            except (TypeError, ValueError):
                raise DjangoValidationError({"value": "This setting must be a number."})
        if self.value_type == self.ValueType.BOOLEAN and self.value.lower() not in {
            "true", "false", "1", "0", ""
        }:
            raise DjangoValidationError({"value": "This setting must be true or false."})
        if self.value_type == self.ValueType.JSON and self.value:
            import json

            try:
                json.loads(self.value)
            except ValueError:
                raise DjangoValidationError({"value": "This setting must be valid JSON."})

    @property
    def typed_value(self):
        """Returns the setting in its declared Python type."""
        if self.value_type == self.ValueType.NUMBER:
            try:
                return float(self.value)
            except (TypeError, ValueError):
                return None
        if self.value_type == self.ValueType.BOOLEAN:
            return self.value.lower() in {"true", "1"}
        if self.value_type == self.ValueType.JSON:
            import json

            try:
                return json.loads(self.value or "{}")
            except ValueError:
                return {}
        return self.value


class ContentPage(BaseModel, PublishableModel):
    """An editable public page: about, delivery policy, terms, FAQ…"""

    slug = models.SlugField(max_length=180, unique=True, db_index=True)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True, help_text="HTML authored in the dashboard.")
    excerpt = models.CharField(max_length=300, blank=True)
    hero_image = models.ImageField(upload_to="cms/pages/", null=True, blank=True)
    is_system = models.BooleanField(default=False, help_text="Required page; cannot be deleted.")
    show_in_footer = models.BooleanField(default=True)
    show_in_header = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)
    canonical_url = models.URLField(blank=True)
    noindex = models.BooleanField(default=False)

    class Meta:
        db_table = "cms_content_page"
        ordering = ["position", "title"]

    def __str__(self) -> str:
        return self.title

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(ContentPage, self.title)
        super().save(*a, **kw)

    @property
    def absolute_path(self) -> str:
        return f"/page/{self.slug}"


class Banner(BaseModel):
    """Homepage hero / promotional banner."""

    title = models.CharField(max_length=150)
    subtitle = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to="cms/banners/", null=True, blank=True)
    cta_label = models.CharField(max_length=60, blank=True)
    cta_url = models.CharField(max_length=300, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "cms_banner"
        ordering = ["position", "-created_at"]

    def __str__(self) -> str:
        return self.title


class StoreLocation(BaseModel):
    """Physical pickup point shown at checkout and in the footer."""

    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    phone = models.CharField(max_length=16, blank=True)
    email = models.EmailField(blank=True)
    opening_hours = models.CharField(max_length=200, blank=True)
    google_maps_url = models.URLField(blank=True)
    is_pickup_point = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cms_store_location"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} — {self.city}"
