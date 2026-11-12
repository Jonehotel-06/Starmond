"""Shared helpers: money maths, quantity validation, pagination params."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.utils.text import slugify as django_slugify

TWO_PLACES = Decimal("0.01")


def money(value) -> Decimal:
    """Coerce any numeric input to a 2dp Decimal without float drift."""
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def to_kobo(amount) -> int:
    """Paystack speaks the smallest currency unit (kobo for NGN)."""
    return int((money(amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_kobo(kobo: int) -> Decimal:
    return money(Decimal(str(kobo)) / 100)


def positive_int(value, field: str = "quantity", minimum: int = 1, maximum: int = 10_000) -> int:
    from apps.core.exceptions import ValidationError

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number.")
    if parsed < minimum:
        raise ValidationError(f"{field} must be at least {minimum}.")
    if parsed > maximum:
        raise ValidationError(f"{field} may not exceed {maximum}.")
    return parsed


def unique_slug(model, value: str, field: str = "slug", max_length: int = 200) -> str:
    """Generate a collision-free slug for ``model``."""
    base = django_slugify(value)[:max_length] or "item"
    candidate = base
    counter = 2
    while model._default_manager.filter(**{field: candidate}).exists():
        suffix = f"-{counter}"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def mask_email(email: str) -> str:
    try:
        local, domain = email.split("@", 1)
    except (ValueError, AttributeError):
        return "***"
    if len(local) <= 2:
        return f"{local[0] if local else '*'}***@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"


_SAFE_REF = re.compile(r"^[A-Za-z0-9_\-:.]+$")


def is_safe_reference(value: str) -> bool:
    return bool(value) and bool(_SAFE_REF.match(value)) and len(value) <= 128
