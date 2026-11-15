"""Production settings — hardened. Validates required configuration at startup."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import config as env

DEBUG = False

if SECRET_KEY == "insecure-dev-only-change-me":  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")

# HTTPS / cookie hardening
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_HSTS_SECONDS = env("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# Paystack keys are mandatory in production.
if not PAYSTACK_SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("PAYSTACK_SECRET_KEY must be set in production.")

if PAYSTACK_BASE_URL != "https://api.paystack.co":  # noqa: F405
    raise ImproperlyConfigured("PAYSTACK_BASE_URL must not be overridden in production.")

if "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list explicit hosts in production.")

# MySQL is mandatory in production.
if DB_ENGINE != "mysql":  # noqa: F405
    raise ImproperlyConfigured("Production requires MySQL (DB_ENGINE=mysql).")

# Transactional email provider must be configured.
if EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":  # noqa: F405
    raise ImproperlyConfigured("Configure a real EMAIL_BACKEND in production.")

LOGGING["root"]["level"] = env("DJANGO_LOG_LEVEL", default="WARNING")  # noqa: F405
