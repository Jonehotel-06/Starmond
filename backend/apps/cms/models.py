from django.db import models

from apps.core.models import TimeStampedModel

DEFAULT_BUSINESS_SETTINGS = {
    "business_name": "STARMOND TECHNOLOGY LIMITED",
    "business_description": "Multi-category online retail: electrical, fashion, electronics, home and more.",
    "contact_email": "support@starmond.example",
    "contact_phone": "",
    "business_address": "",
    "currency": "NGN",
    "currency_symbol": "₦",
    "social_links": {"facebook": "", "instagram": "", "x": "", "whatsapp": ""},
    "logo_key": "",
    "favicon_key": "",
    "homepage_hero": {"title": "", "subtitle": "", "cta_label": "Shop now", "cta_url": "/shop/", "image_key": ""},
    "footer_text": "",
    "support_hours": "",
    "refund_window_days": "7",
}


class BusinessSetting(models.Model):
    """Single-row editable business configuration (never hardcode content)."""
    key = "business"  # singleton marker
    values = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "cms_business_setting"

    def __str__(self):
        return "Business settings"


class Page(TimeStampedModel):
    """Informational / policy pages (About, Privacy, Terms, Shipping,
    Returns & Refunds, FAQ, Contact...)."""
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True)
    body = models.TextField(blank=True, help_text="HTML or markdown content managed by staff.")
    excerpt = models.CharField(max_length=300, blank=True)
    is_published = models.BooleanField(default=False, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    canonical_url = models.URLField(max_length=300, blank=True)

    class Meta:
        db_table = "cms_page"
        ordering = ["display_order", "title"]

    def __str__(self):
        return self.title

    def effective_seo(self):
        return {
            "title": self.seo_title or f"{self.title} | STARMOND TECHNOLOGY LIMITED",
            "description": self.seo_description or self.excerpt,
            "canonical_url": self.canonical_url,
        }


class HomepageSection(TimeStampedModel):
    class Kind(models.TextChoices):
        HERO = "hero", "Hero"
        FEATURED_PRODUCTS = "featured_products", "Featured products"
        NEW_ARRIVALS = "new_arrivals", "New arrivals"
        BEST_SELLERS = "best_sellers", "Best sellers"
        CATEGORY_SPOTLIGHT = "category_spotlight", "Category spotlight"
        BANNER = "banner", "Promotional banner"
        CUSTOM = "custom", "Custom HTML/JSON block"

    kind = models.CharField(max_length=24, choices=Kind.choices)
    title = models.CharField(max_length=150, blank=True)
    subtitle = models.CharField(max_length=250, blank=True)
    config = models.JSONField(default=dict, blank=True,
        help_text='e.g. {"category_slug": "electrical", "limit": 8, "cta_url": "/shop/electrical/"}')
    image_key = models.CharField(max_length=400, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "cms_homepage_section"
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.kind}:{self.title or self.pk}"


class Banner(TimeStampedModel):
    title = models.CharField(max_length=150)
    subtitle = models.CharField(max_length=250, blank=True)
    image_key = models.CharField(max_length=400, blank=True)
    link_url = models.CharField(max_length=300, blank=True)
    placement = models.CharField(max_length=40, default="homepage", db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cms_banner"
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        return self.title
