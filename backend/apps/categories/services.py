from django.conf import settings
from django.db import transaction

from apps.core.exceptions import ServiceError
from apps.core.slugs import unique_slugify

from .models import Category


class CategoryService:
    @staticmethod
    @transaction.atomic
    def create_or_update(category, *, name, slug=None, parent=None, **fields):
        """Validate hierarchy, uniqueness and depth, then persist."""
        if parent is not None:
            if not parent.is_active and not getattr(category, "pk", None):
                raise ServiceError("Cannot create a subcategory under an inactive parent.", code="inactive_parent")
            if category.pk and parent.pk == category.pk:
                raise ServiceError("A category cannot be its own parent.", code="invalid_parent")
            if category.pk and parent in CategoryService.descendants(category):
                raise ServiceError("Cannot move a category under its own descendant.", code="cycle_detected")
            new_depth = parent.depth + 1
        else:
            new_depth = 0
        if new_depth + 1 > settings.MAX_CATEGORY_DEPTH:
            raise ServiceError(
                f"Maximum category nesting depth ({settings.MAX_CATEGORY_DEPTH}) exceeded.",
                code="max_depth_exceeded",
            )
        if slug:
            if Category.objects.filter(slug=slug).exclude(pk=getattr(category, "pk", None)).exists():
                raise ServiceError("A category with this slug already exists.", code="duplicate_slug", status_code=409)
        else:
            slug = unique_slugify(category, name, queryset=Category.objects.all())
        category.name = name
        category.slug = slug
        category.parent = parent
        for key, value in fields.items():
            setattr(category, key, value)
        category.full_clean(exclude=["slug", "image", "banner_image", "og_image"])
        category.save()
        return category

    @staticmethod
    def descendants(category):
        result, stack = [], list(Category.objects.filter(parent=category))
        while stack:
            node = stack.pop()
            result.append(node)
            stack.extend(Category.objects.filter(parent=node))
        return result

    @staticmethod
    @transaction.atomic
    def safe_delete(category):
        """Block deletion when products or subcategories depend on it."""
        product_count = category.products.count()
        child_count = category.children.count()
        if product_count or child_count:
            raise ServiceError(
                f"Cannot delete: {product_count} product(s) and {child_count} subcategory(ies) still linked. "
                "Deactivate the category or move its contents first.",
                code="category_in_use", status_code=409,
            )
        category.delete()

    @staticmethod
    def deactivate_tree(category):
        """Deactivate a category and all descendants in one operation."""
        with transaction.atomic():
            ids = [category.pk] + [c.pk for c in CategoryService.descendants(category)]
            Category.objects.filter(pk__in=ids).update(is_active=False)
        return len(ids)

    @staticmethod
    def reorder(pairs):
        """pairs: list of {"id": int, "display_order": int}."""
        with transaction.atomic():
            for pair in pairs:
                Category.objects.filter(pk=pair["id"]).update(display_order=pair["display_order"])
