from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.core.models import TimeStampedModel


class CategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def roots(self):
        return self.filter(parent__isnull=True)


class Category(TimeStampedModel):
    """Dynamic catalogue category. Unlimited categories, nested subcategories
    up to settings.MAX_CATEGORY_DEPTH. Never hardcoded."""
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, db_index=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    banner_image = models.ImageField(upload_to="categories/banners/", blank=True, null=True)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    # SEO
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    seo_keywords = models.CharField(max_length=255, blank=True)
    og_image = models.ImageField(upload_to="categories/og/", blank=True, null=True)
    canonical_url = models.URLField(max_length=300, blank=True)
    # Status
    is_active = models.BooleanField(default=True, db_index=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        db_table = "categories_category"
        ordering = ["display_order", "name"]
        verbose_name_plural = "categories"
        indexes = [models.Index(fields=["parent", "display_order"]), models.Index(fields=["is_active", "display_order"])]

    def __str__(self):
        return self.name

    @property
    def depth(self):
        depth, node = 0, self
        while node.parent_id:
            node = node.parent
            depth += 1
        return depth

    @property
    def url_path(self):
        """Public URL path e.g. /shop/electrical/cables/"""
        parts, node = [], self
        while node:
            parts.append(node.slug)
            node = node.parent
        return "/shop/" + "/".join(reversed(parts)) + "/"

    @property
    def breadcrumb(self):
        parts, node = [], self
        while node:
            parts.append({"name": node.name, "slug": node.slug, "url_path": node.url_path})
            node = node.parent
        return list(reversed(parts))

    @property
    def image_url(self):
        return self.image.url if self.image else None

    @property
    def banner_image_url(self):
        return self.banner_image.url if self.banner_image else None

    def effective_seo(self):
        return {
            "title": self.seo_title or f"{self.name} | STARMOND TECHNOLOGY LIMITED",
            "description": self.seo_description or (self.description[:300] if self.description else f"Shop {self.name} at STARMOND TECHNOLOGY LIMITED."),
            "keywords": self.seo_keywords,
            "canonical_url": self.canonical_url,
            "og_image": self.og_image.url if self.og_image else self.image_url,
        }
