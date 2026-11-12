"""Development settings — NEVER deploy with this module."""
from .base import *  # noqa: F401,F403
from .base import env, env_bool, env_list

DEBUG = True
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "*") or ["*"]

# Permissive CORS for the locally developed vanilla-JS frontend only.
CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

# Local development must never touch live Paystack money movement.
if PAYSTACK_MODE == "live" and not env_bool("PAYSTACK_ALLOW_LIVE_IN_DEBUG", False):  # noqa: F405
    raise RuntimeError(
        "PAYSTACK_MODE=live is blocked while DEBUG=True. "
        "Use test keys, or explicitly set PAYSTACK_ALLOW_LIVE_IN_DEBUG=True if you truly mean it."
    )

LOGGING["root"]["level"] = env("LOG_LEVEL", "DEBUG")  # noqa: F405
