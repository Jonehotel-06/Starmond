from django.db import models

DEFAULT_SEO_SETTINGS = {
    "default_title_template": "{title} | STARMOND TECHNOLOGY LIMITED",
    "default_meta_description": "Shop electrical supplies, fashion, electronics, gadgets and home products at STARMOND TECHNOLOGY LIMITED. Nationwide delivery in Nigeria.",
    "default_og_site_name": "STARMOND TECHNOLOGY LIMITED",
    "canonical_base_url": "",
    "homepage_seo_title": "STARMOND TECHNOLOGY LIMITED — Electrical, Fashion, Electronics & Home Products in Nigeria",
    "homepage_seo_description": "",
    "homepage_og_image_key": "",
    "robots_meta_default": "index, follow",
    "enable_prerender": True,
}


class SEOSetting(models.Model):
    """Singleton global SEO defaults."""
    values = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seo_setting"

    def __str__(self):
        return "Global SEO settings"


class SitemapVersion(models.Model):
    """Bumped whenever catalogue content changes so the sitemap cache and
    lastmod values stay accurate."""
    pk_lock = models.BooleanField(primary_key=True, default=True)
    version = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seo_sitemap_version"
