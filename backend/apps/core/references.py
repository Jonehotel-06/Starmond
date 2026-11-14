"""Human-readable, non-sequential business reference generators."""
import secrets
import string

from django.utils import timezone

_ALPHABET = string.ascii_uppercase + string.digits


def _suffix(n=4):
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def order_reference():
    return f"ORD-{timezone.localdate().strftime('%Y%m%d')}-{_suffix(4)}"


def payment_reference():
    return f"PAY-{timezone.localdate().strftime('%Y%m%d')}-{_suffix(6)}"


def refund_reference():
    return f"REF-{timezone.localdate().strftime('%Y%m%d')}-{_suffix(4)}"


def cart_token():
    return f"CRT-{secrets.token_hex(16)}"


def idempotency_key():
    return secrets.token_hex(16)
