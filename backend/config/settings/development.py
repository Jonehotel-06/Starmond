"""Development settings — NEVER deploy with this module."""
from decouple import Csv

from .base import *  # noqa: F401,F403
from .base import config

DEBUG = True
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="*", cast=Csv()) or ["*"]

# Permissive CORS for the locally developed vanilla-JS frontend only.
CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# Local development must never touch live Paystack money movement.
if PAYSTACK_MODE == "live" and not config(  # noqa: F405
    "PAYSTACK_ALLOW_LIVE_IN_DEBUG", default=False, cast=bool
):
    raise RuntimeError(
        "PAYSTACK_MODE=live is blocked while DEBUG=True. "
        "Use test keys, or explicitly set PAYSTACK_ALLOW_LIVE_IN_DEBUG=True if you truly mean it."
    )

LOGGING["root"]["level"] = config("LOG_LEVEL", default="DEBUG")  # noqa: F405