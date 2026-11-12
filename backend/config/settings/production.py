"""Production settings — hardened defaults, fails closed on misconfiguration."""
from .base import *  # noqa: F401,F403
from .base import env, env_bool, env_list

DEBUG = False

if SECRET_KEY in {"", "unsafe-dev-key-change-me"}:  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set to a strong unique value in production.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set in production.")

if not PAYSTACK_SECRET_KEY:  # noqa: F405
    raise RuntimeError("PAYSTACK_SECRET_KEY must be configured in production.")

# TLS / cookies
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# CORS must be explicit in production.
CORS_ALLOW_ALL_ORIGINS = False
if not CORS_ALLOWED_ORIGINS:  # noqa: F405
    raise RuntimeError("CORS_ALLOWED_ORIGINS must be set in production.")

# Hashed static file names. In Django 5 this must be expressed through STORAGES
# (setting STATICFILES_STORAGE alongside STORAGES is an error).
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
    },
}

if EMAIL_BACKEND.endswith("console.EmailBackend"):  # noqa: F405
    raise RuntimeError("A real EMAIL_BACKEND must be configured in production.")
