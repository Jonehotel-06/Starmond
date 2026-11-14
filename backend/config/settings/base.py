"""
STARMOND TECHNOLOGY LIMITED — base Django settings.

Shared by development and production settings modules.
Every environment-specific or secret value is read with python-decouple's
`config` (from the environment first, then from the project's .env file).

Requires:  pip install python-decouple
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from decouple import AutoConfig, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Look for .env / settings.ini in the project root regardless of where Django
# is started from.
config = AutoConfig(search_path=BASE_DIR)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = config("DJANGO_SECRET_KEY", default="unsafe-dev-key-change-me")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

BUSINESS_NAME = config("BUSINESS_NAME", default="STARMOND TECHNOLOGY LIMITED")
DEFAULT_CURRENCY = config("DEFAULT_CURRENCY", default="NGN")
SUPPORTED_CURRENCIES = config("SUPPORTED_CURRENCIES", default="NGN", cast=Csv())
SITE_URL = config("SITE_URL", default="http://localhost:8000").rstrip("/")
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000").rstrip("/")

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
DB_ENGINE = config("DB_ENGINE", default="sqlite").lower()

if DB_ENGINE in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="starmond"),
            "USER": config("DB_USER", default="starmond"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="127.0.0.1"),
            "PORT": config("DB_PORT", default="5432"),
            "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
            "ATOMIC_REQUESTS": False,
            "OPTIONS": {"connect_timeout": 10},
        }
    }
elif DB_ENGINE in {"mysql", "mariadb"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": config("DB_NAME", default="starmond"),
            "USER": config("DB_USER", default="starmond"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="127.0.0.1"),
            "PORT": config("DB_PORT", default="3306"),
            "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
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
            "NAME": Path(config("DB_NAME", default=str(BASE_DIR / "db.sqlite3"))),
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
    "PAGE_SIZE": config("API_PAGE_SIZE", default=20, cast=int),
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
        "anon": config("THROTTLE_ANON", default="120/min"),
        "user": config("THROTTLE_USER", default="600/min"),
        "auth": config("THROTTLE_AUTH", default="10/min"),
        "checkout": config("THROTTLE_CHECKOUT", default="30/min"),
        "review": config("THROTTLE_REVIEW", default="5/hour"),
        "webhook": config("THROTTLE_WEBHOOK", default="600/min"),
        "search": config("THROTTLE_SEARCH", default="120/min"),
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("JWT_ACCESS_MINUTES", default=45, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_DAYS", default=14, cast=int)),
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
TIME_ZONE = config("TIME_ZONE", default="Africa/Lagos")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = config("STATIC_URL", default="/static/")
STATIC_ROOT = Path(config("STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))
MEDIA_URL = config("MEDIA_URL", default="/media/")
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))
STORAGES = {
    "default": {"BACKEND": config(
        "DEFAULT_FILE_STORAGE",
        default="django.core.files.storage.FileSystemStorage",
    )},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MAX_UPLOAD_SIZE_BYTES = config("MAX_UPLOAD_SIZE_BYTES", default=8 * 1024 * 1024, cast=int)

# Category nesting guard. The taxonomy itself is unlimited (categories are
# created freely in the dashboard); this only prevents absurdly deep URLs.
MAX_CATEGORY_DEPTH = config("MAX_CATEGORY_DEPTH", default=25, cast=int)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# Django's default LocMemCache is per-process, so DRF throttles and cached
# settings would be counted separately by every Gunicorn worker. Set REDIS_URL
# in production and the cache — and therefore throttling — becomes shared.
REDIS_URL = config("REDIS_URL", default="")
CACHE_TIMEOUT = config("CACHE_TIMEOUT", default=300, cast=int)
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "TIMEOUT": CACHE_TIMEOUT,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "starmond-local",
            "TIMEOUT": CACHE_TIMEOUT,
        }
    }

# ---------------------------------------------------------------------------
# CORS / CSRF / cookies
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000",
    cast=Csv(),
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

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:8000,http://localhost:3000",
    cast=Csv(),
)
CSRF_COOKIE_HTTPONLY = False          # JS frontend must read it for the X-CSRFToken header
CSRF_COOKIE_SAMESITE = config("CSRF_COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=False, cast=bool)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = config("SESSION_COOKIE_SAMESITE", default="Lax")
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=False, cast=bool)
SESSION_COOKIE_AGE = config("SESSION_COOKIE_AGE", default=60 * 60 * 24 * 7, cast=int)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Paystack
# ---------------------------------------------------------------------------
PAYSTACK_BASE_URL = config("PAYSTACK_BASE_URL", default="https://api.paystack.co")
PAYSTACK_PUBLIC_KEY = config("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_SECRET_KEY = config("PAYSTACK_SECRET_KEY", default="")
# Paystack signs webhooks with the account secret key; an explicit override is
# supported for accounts using a separate webhook secret.
PAYSTACK_WEBHOOK_SECRET = config("PAYSTACK_WEBHOOK_SECRET", default="") or PAYSTACK_SECRET_KEY
PAYSTACK_CALLBACK_URL = config("PAYSTACK_CALLBACK_URL", default=f"{FRONTEND_URL}/checkout/callback")
PAYSTACK_MODE = config("PAYSTACK_MODE", default="test")          # "test" | "live"
PAYSTACK_TIMEOUT_SECONDS = config("PAYSTACK_TIMEOUT_SECONDS", default=20, cast=int)
PAYSTACK_MAX_RETRIES = config("PAYSTACK_MAX_RETRIES", default=3, cast=int)
PAYSTACK_CHANNELS = config(
    "PAYSTACK_CHANNELS",
    default="card,bank,ussd,bank_transfer,qr",
    cast=Csv(),
)
# Guard rail: refuse live credentials while DEBUG is on.
PAYSTACK_ALLOW_LIVE_IN_DEBUG = config("PAYSTACK_ALLOW_LIVE_IN_DEBUG", default=False, cast=bool)

# ---------------------------------------------------------------------------
# Business rules (Section 45) — configurable, never hardcoded in views
# ---------------------------------------------------------------------------
ORDER_EXPIRY_MINUTES = config("ORDER_EXPIRY_MINUTES", default=60, cast=int)
STOCK_RESERVATION_MINUTES = config("STOCK_RESERVATION_MINUTES", default=60, cast=int)
LOW_STOCK_DEFAULT_THRESHOLD = config("LOW_STOCK_DEFAULT_THRESHOLD", default=5, cast=int)
MAX_CART_ITEM_QUANTITY = config("MAX_CART_ITEM_QUANTITY", default=50, cast=int)
MAX_CART_LINES = config("MAX_CART_LINES", default=50, cast=int)
MAX_DISCOUNT_PERCENTAGE = config("MAX_DISCOUNT_PERCENTAGE", default=100, cast=int)
REVIEW_EDIT_WINDOW_DAYS = config("REVIEW_EDIT_WINDOW_DAYS", default=30, cast=int)
REFUND_MAX_DAYS_AFTER_DELIVERY = config("REFUND_MAX_DAYS_AFTER_DELIVERY", default=30, cast=int)
IDEMPOTENCY_KEY_TTL_HOURS = config("IDEMPOTENCY_KEY_TTL_HOURS", default=24, cast=int)
AUDIT_RETENTION_DAYS = config("AUDIT_RETENTION_DAYS", default=730, cast=int)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=15, cast=int)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="STARMOND <no-reply@starmond.com>")
SERVER_EMAIL = config("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
EMAIL_FAIL_SILENTLY = config("EMAIL_FAIL_SILENTLY", default=True, cast=bool)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = config("LOG_LEVEL", default="INFO")
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