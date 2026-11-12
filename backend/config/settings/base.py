"""
STARMOND TECHNOLOGY LIMITED — base Django settings.

Shared by development and production settings modules.
Every environment-specific or secret value is read from the environment.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise ImproperlyConfiguredError(f"Missing required environment variable: {key}")
    return value


def env_bool(key: str, default: bool = False) -> bool:
    return str(os.environ.get(key, str(default))).strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class ImproperlyConfiguredError(RuntimeError):
    """Raised when a mandatory environment variable is absent."""


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", "unsafe-dev-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

BUSINESS_NAME = env("BUSINESS_NAME", "STARMOND TECHNOLOGY LIMITED")
DEFAULT_CURRENCY = env("DEFAULT_CURRENCY", "NGN")
SUPPORTED_CURRENCIES = env_list("SUPPORTED_CURRENCIES", "NGN")
SITE_URL = env("SITE_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.customers",
    "apps.categories",
    "apps.products",
    "apps.inventory",
    "apps.cart",
    "apps.orders",
    "apps.payments",
    "apps.refunds",
    "apps.shipping",
    "apps.promotions",
    "apps.reviews",
    "apps.notifications",
    "apps.emails",
    "apps.dashboard",
    "apps.reports",
    "apps.cms",
    "apps.media_lib",
    "apps.seo",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database — MySQL 8+ / PostgreSQL in production, SQLite for local dev/tests
# ---------------------------------------------------------------------------
DB_ENGINE = env("DB_ENGINE", "sqlite").lower()

if DB_ENGINE in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "starmond"),
            "USER": env("DB_USER", "starmond"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "5432"),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
            "ATOMIC_REQUESTS": False,
            "OPTIONS": {"connect_timeout": 10},
        }
    }
elif DB_ENGINE in {"mysql", "mariadb"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME", "starmond"),
            "USER": env("DB_USER", "starmond"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "3306"),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
            "ATOMIC_REQUESTS": False,
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(env("DB_NAME", str(BASE_DIR / "db.sqlite3"))),
            "OPTIONS": {"timeout": 20},
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": env_int("API_PAGE_SIZE", 20),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", "120/min"),
        "user": env("THROTTLE_USER", "600/min"),
        "auth": env("THROTTLE_AUTH", "10/min"),
        "checkout": env("THROTTLE_CHECKOUT", "30/min"),
        "review": env("THROTTLE_REVIEW", "5/hour"),
        "webhook": env("THROTTLE_WEBHOOK", "600/min"),
        "search": env("THROTTLE_SEARCH", "120/min"),
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 45)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 14)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "STARMOND TECHNOLOGY LIMITED API",
    "DESCRIPTION": "Single-owner multi-category e-commerce platform backend.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# Internationalisation / time
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-ng"
TIME_ZONE = env("TIME_ZONE", "Africa/Lagos")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = env("STATIC_URL", "/static/")
STATIC_ROOT = Path(env("STATIC_ROOT", str(BASE_DIR / "staticfiles")))
MEDIA_URL = env("MEDIA_URL", "/media/")
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
STORAGES = {
    "default": {"BACKEND": env(
        "DEFAULT_FILE_STORAGE",
        "django.core.files.storage.FileSystemStorage",
    )},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MAX_UPLOAD_SIZE_BYTES = env_int("MAX_UPLOAD_SIZE_BYTES", 8 * 1024 * 1024)

# Category nesting guard. The taxonomy itself is unlimited (categories are
# created freely in the dashboard); this only prevents absurdly deep URLs.
MAX_CATEGORY_DEPTH = env_int("MAX_CATEGORY_DEPTH", 25)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# Django's default LocMemCache is per-process, so DRF throttles and cached
# settings would be counted separately by every Gunicorn worker. Set REDIS_URL
# in production and the cache — and therefore throttling — becomes shared.
REDIS_URL = env("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "TIMEOUT": env_int("CACHE_TIMEOUT", 300),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "starmond-local",
            "TIMEOUT": env_int("CACHE_TIMEOUT", 300),
        }
    }

# ---------------------------------------------------------------------------
# CORS / CSRF / cookies
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000",
)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-request-id",
    "x-idempotency-key",
    "x-cart-token",
]
CORS_EXPOSE_HEADERS = ["X-Request-ID", "X-Idempotent-Replay"]

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://localhost:3000")
CSRF_COOKIE_HTTPONLY = False          # JS frontend must read it for the X-CSRFToken header
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 7)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Paystack
# ---------------------------------------------------------------------------
PAYSTACK_BASE_URL = env("PAYSTACK_BASE_URL", "https://api.paystack.co")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", "")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
# Paystack signs webhooks with the account secret key; an explicit override is
# supported for accounts using a separate webhook secret.
PAYSTACK_WEBHOOK_SECRET = env("PAYSTACK_WEBHOOK_SECRET", "") or env("PAYSTACK_SECRET_KEY", "")
PAYSTACK_CALLBACK_URL = env("PAYSTACK_CALLBACK_URL", f"{FRONTEND_URL}/checkout/callback")
PAYSTACK_MODE = env("PAYSTACK_MODE", "test")          # "test" | "live"
PAYSTACK_TIMEOUT_SECONDS = env_int("PAYSTACK_TIMEOUT_SECONDS", 20)
PAYSTACK_MAX_RETRIES = env_int("PAYSTACK_MAX_RETRIES", 3)
PAYSTACK_CHANNELS = env_list("PAYSTACK_CHANNELS", "card,bank,ussd,bank_transfer,qr")
# Guard rail: refuse live credentials while DEBUG is on.
PAYSTACK_ALLOW_LIVE_IN_DEBUG = env_bool("PAYSTACK_ALLOW_LIVE_IN_DEBUG", False)

# ---------------------------------------------------------------------------
# Business rules (Section 45) — configurable, never hardcoded in views
# ---------------------------------------------------------------------------
ORDER_EXPIRY_MINUTES = env_int("ORDER_EXPIRY_MINUTES", 60)
STOCK_RESERVATION_MINUTES = env_int("STOCK_RESERVATION_MINUTES", 60)
LOW_STOCK_DEFAULT_THRESHOLD = env_int("LOW_STOCK_DEFAULT_THRESHOLD", 5)
MAX_CART_ITEM_QUANTITY = env_int("MAX_CART_ITEM_QUANTITY", 50)
MAX_CART_LINES = env_int("MAX_CART_LINES", 50)
MAX_DISCOUNT_PERCENTAGE = env_int("MAX_DISCOUNT_PERCENTAGE", 100)
REVIEW_EDIT_WINDOW_DAYS = env_int("REVIEW_EDIT_WINDOW_DAYS", 30)
REFUND_MAX_DAYS_AFTER_DELIVERY = env_int("REFUND_MAX_DAYS_AFTER_DELIVERY", 30)
IDEMPOTENCY_KEY_TTL_HOURS = env_int("IDEMPOTENCY_KEY_TTL_HOURS", 24)
AUDIT_RETENTION_DAYS = env_int("AUDIT_RETENTION_DAYS", 730)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 15)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "STARMOND <no-reply@starmond.com>")
SERVER_EMAIL = env("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_FAIL_SILENTLY = env_bool("EMAIL_FAIL_SILENTLY", True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {request_id} {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {name} {message}", "style": "{"},
    },
    "filters": {
        "request_id": {"()": "apps.core.logging.RequestIDLogFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "payments": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
