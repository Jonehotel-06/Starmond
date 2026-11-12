"""CategoryService — tree operations and category lookups."""
from __future__ import annotations

from typing import Iterable

from django.db import transaction
from django.db.models import Q

from apps.categories.models import Category
from apps.core.exceptions import ConflictError, NotFound, ValidationError
from apps.core.models import PublishableModel
from apps.core.utils import unique_slug


class CategoryService:
    @staticmethod
    def get_public(slug_or_path: str) -> Category:
        category = (
            Category.objects.public()
            .filter(Q(slug=slug_or_path) | Q(path=slug_or_path))
            .first()
        )
        if category is None:
            raise NotFound("Category not found.")
        return category

    @staticmethod
    @transaction.atomic
    def create(*, name: str, parent: Category | None = None, **fields) -> Category:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Category name is required.")
        if parent is not None and Category.objects.filter(parent=parent, name__iexact=name).exists():
            raise ConflictError(f"A subcategory named '{name}' already exists here.")
        slug = fields.pop("slug", None) or unique_slug(Category, name)
        category = Category(name=name, parent=parent, slug=slug, **fields)
        category.full_clean(exclude=["path", "depth"])
        category.save()
        return category

    @staticmethod
    @transaction.atomic
    def update(category: Category, **fields) -> Category:
        allowed = {
            "name", "slug", "description", "short_description", "image", "icon",
            "position", "is_active", "is_featured", "status", "meta_title",
            "meta_description", "meta_keywords", "canonical_url", "parent",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValidationError(f"Unsupported field(s): {', '.join(sorted(unknown))}.")
        for key, value in fields.items():
            setattr(category, key, value)
        if category.status == PublishableModel.Status.PUBLISHED and not category.published_at:
            from django.utils import timezone
            category.published_at = timezone.now()
        category.full_clean(exclude=["path", "depth"])
        category.save()
        return category

    @staticmethod
    @transaction.atomic
    def delete(category: Category) -> None:
        if category.children.exists():
            raise ConflictError("Move or delete subcategories before deleting this category.")
        if category.products.exists():
            raise ConflictError(
                "This category still contains products. Reassign them before deleting the category."
            )
        category.delete()

    @staticmethod
    def tree(public_only: bool = True) -> list[dict]:
        """Returns the full nested category tree in a single query."""
        qs = Category.objects.all()
        if public_only:
            qs = qs.public()
        nodes = list(qs.order_by("depth", "position", "name"))

        serialised = {}
        for node in nodes:
            serialised[node.pk] = {
                "id": str(node.id),
                "name": node.name,
                "slug": node.slug,
                "path": node.path,
                "depth": node.depth,
                "status": node.status,
                "is_featured": node.is_featured,
                "image": node.image.url if node.image else None,
                "description": node.short_description or node.description[:200],
                "meta_title": node.meta_title or node.name,
                "meta_description": node.meta_description,
                "url": node.absolute_path,
                "product_count": 0,
                "children": [],
            }

        roots: list[dict] = []
        for node in nodes:
            item = serialised[node.pk]
            parent = serialised.get(node.parent_id) if node.parent_id else None
            if parent is not None:
                parent["children"].append(item)
            elif node.parent_id is None:
                roots.append(item)
        return roots

    @staticmethod
    def breadcrumb_for(category: Category) -> list[dict]:
        return category.breadcrumb()

    @staticmethod
    def featured(limit: int = 12) -> Iterable[Category]:
        return Category.objects.public().filter(is_featured=True)[:limit]
