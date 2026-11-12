"""
Unlimited dynamic categories and subcategories.

There is no fixed taxonomy: administrators create, rename, move and nest
categories at will (Section 45 rule 2). The tree is stored with a parent
pointer, a materialised ``path`` and a computed ``depth`` so breadcrumbs and
public URLs stay cheap to build at any depth.

``MAX_CATEGORY_DEPTH`` is an operational guard against pathological trees
(a category nested thousands of levels deep would generate absurd URLs). It
defaults to 25 and can be raised or lowered through the environment; it is not
a taxonomy limit.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.urls import reverse

from apps.core.models import BaseModel, PublishableModel
from apps.core.utils import unique_slug

MAX_CATEGORY_DEPTH = getattr(settings, "MAX_CATEGORY_DEPTH", 10)


class CategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def public(self):
        return self.active().filter(status=PublishableModel.Status.PUBLISHED)

    def roots(self):
        return self.filter(parent__isnull=True)

    def with_products(self):
        return self.filter(products__isnull=False).distinct()


class CategoryManager(models.Manager.from_queryset(CategoryQuerySet)):
    def public(self):
        return self.get_queryset().public()


class Category(BaseModel, PublishableModel):
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    name = models.CharField(max_length=150, db_index=True)
    slug = models.SlugField(max_length=180, unique=True, db_index=True)
    path = models.CharField(max_length=600, blank=True, db_index=True)
    depth = models.PositiveSmallIntegerField(default=0, db_index=True)
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to="categories/", null=True, blank=True)
    icon = models.CharField(max_length=80, blank=True)
    position = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, help_text="Shown in the storefront navigation.")

    # SEO (Section 25)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)
    meta_keywords = models.CharField(max_length=255, blank=True)
    canonical_url = models.URLField(blank=True)

    objects = CategoryManager()

    class Meta:
        db_table = "categories_category"
        ordering = ["position", "name"]
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=["parent", "position"]),
            models.Index(fields=["is_active", "status"]),
            models.Index(fields=["path"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_category_name_per_parent"),
        ]

    def __str__(self) -> str:
        return self.path or self.name

    # -- tree maintenance --------------------------------------------------
    def clean(self):
        if self.parent_id and self.parent_id == self.pk:
            raise DjangoValidationError({"parent": "A category cannot be its own parent."})
        if self.parent_id:
            # reject cycles: walk up the ancestor chain
            ancestor = self.parent
            seen = {self.pk}
            while ancestor is not None:
                if ancestor.pk in seen:
                    raise DjangoValidationError({"parent": "Circular category hierarchy detected."})
                seen.add(ancestor.pk)
                ancestor = ancestor.parent

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(Category, self.name)
        parent = self.parent
        self.depth = (parent.depth + 1) if parent else 0
        if self.depth > MAX_CATEGORY_DEPTH:
            raise DjangoValidationError(
                {"parent": f"Categories may not nest deeper than {MAX_CATEGORY_DEPTH} levels."}
            )
        self.path = f"{parent.path}/{self.slug}" if parent and parent.path else (
            f"{parent.slug}/{self.slug}" if parent else self.slug
        )
        super().save(*a, **kw)
        # keep descendants' materialised paths consistent after a move
        for child in self.children.all():
            child.save()

    # -- helpers -----------------------------------------------------------
    @property
    def absolute_path(self) -> str:
        return f"/category/{self.path or self.slug}"

    def get_absolute_url(self) -> str:
        return self.absolute_path

    def ancestors(self) -> list["Category"]:
        chain, node = [], self.parent
        while node is not None:
            chain.append(node)
            node = node.parent
        return list(reversed(chain))

    def breadcrumb(self) -> list[dict]:
        return [{"name": c.name, "slug": c.slug, "path": c.path, "url": c.absolute_path}
                for c in self.ancestors()] + [
            {"name": self.name, "slug": self.slug, "path": self.path, "url": self.absolute_path}
        ]

    def descendant_ids(self, include_self: bool = True) -> list:
        """All descendant ids — used so browsing a parent shows child products."""
        ids = {self.pk} if include_self else set()
        frontier = [self.pk]
        while frontier:
            children = list(
                Category.objects.filter(parent_id__in=frontier).values_list("pk", flat=True)
            )
            ids.update(children)
            frontier = children
        return list(ids)

    @property
    def is_leaf(self) -> bool:
        return not self.children.exists()

    @property
    def product_count(self) -> int:
        return self.products.filter(
            status=PublishableModel.Status.PUBLISHED, deleted_at__isnull=True
        ).count()
