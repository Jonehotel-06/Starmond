"""Decimal money helpers. Floats are NEVER used for monetary arithmetic."""
from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0.00")


def to_decimal(value):
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def naira_to_kobo(amount: Decimal) -> int:
    return int((to_decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def kobo_to_naira(kobo) -> Decimal:
    return (Decimal(int(kobo)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def percent_of(amount: Decimal, percent: Decimal) -> Decimal:
    return (to_decimal(amount) * to_decimal(percent) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
