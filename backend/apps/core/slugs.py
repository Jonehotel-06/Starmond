import re

from django.utils.text import slugify


def unique_slugify(instance, value, slug_field="slug", queryset=None, max_length=80):
    """Generate a slug unique within `queryset` (defaults to the model's own)."""
    base = re.sub(r"-+", "-", slugify(value)).strip("-").lower() or "item"
    base = base[:max_length]
    qs = queryset if queryset is not None else instance.__class__._default_manager.all()
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)
    slug, n = base, 2
    while qs.filter(**{slug_field: slug}).exists():
        suffix = f"-{n}"
        slug = base[: max_length - len(suffix)] + suffix
        n += 1
    return slug
