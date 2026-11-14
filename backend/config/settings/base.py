"""Base settings for STARMOND TECHNOLOGY LIMITED backend.

Secrets come exclusively from environment variables / .env (via python-decouple).
Nothing sensitive is hardcoded. See .env.example for the full contract.
"""
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY", default="insecure-dev-only-change-me")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

FRONTEND_BASE_URL = config("FRONTEND_BASE_URL", default="http://localhost:3000")
SITE_URL = config("SITE_URL", default=FRONTEND_BASE_URL)
API_BASE_URL = config("API_BASE_URL", default="http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third party
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    # Business apps
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
    "apps.media",
    "apps.seo",
    "apps.audit",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
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

# ---------------------------------------------------------------- Database
DB_ENGINE = config("DB_ENGINE", default="mysql")  # "mysql" | "sqlite" (dev/test only)
if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / config("SQLITE_NAME", default="db.sqlite3"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": config("DB_NAME", default="starmond"),
            "USER": config("DB_USER", default="starmond"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="127.0.0.1"),
            "PORT": config("DB_PORT", default="3306"),
            "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES', "
                                "default_storage_engine=InnoDB",
            },
            "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
        }
    }
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

# ---------------------------------------------------------------- Auth / DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.core.throttles.BurstAnonThrottle",
        "apps.core.throttles.StandardUserThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon_burst": config("THROTTLE_ANON", default="240/hour"),
        "user_standard": config("THROTTLE_USER", default="1200/hour"),
        "auth_action": config("THROTTLE_AUTH", default="10/hour"),
        "webhook": config("THROTTLE_WEBHOOK", default="600/minute"),
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # 'format' is a business query-param (report exports), not a renderer suffix
    "URL_FORMAT_OVERRIDE": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "STARMOND TECHNOLOGY LIMITED — E-Commerce API",
    "DESCRIPTION": "Complete multi-category e-commerce backend API (single-owner retail).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/",
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sessions / cookies — secure defaults; tightened in production settings.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # frontend JS must read the CSRF cookie
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="http://localhost:3000", cast=Csv())
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000", cast=Csv())
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["X-Request-ID", "X-Response-Time-Ms", "X-CSRFToken"]

# ---------------------------------------------------------------- I18N / time
LANGUAGE_CODE = "en-ng"
TIME_ZONE = config("DJANGO_TIME_ZONE", default="Africa/Lagos")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- Static / media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Backblaze B2 (S3-compatible). Falls back to local storage when unset (dev).
B2_APPLICATION_KEY_ID = config("B2_APPLICATION_KEY_ID", default="")
B2_APPLICATION_KEY = config("B2_APPLICATION_KEY", default="")
B2_BUCKET_NAME = config("B2_BUCKET_NAME", default="starmond-media")
B2_ENDPOINT_URL = config("B2_ENDPOINT_URL", default="https://s3.us-west-004.backblazeb2.com")
B2_REGION = config("B2_REGION", default="us-west-004")
B2_PUBLIC_BASE_URL = config("B2_PUBLIC_BASE_URL", default="")
B2_MEDIA_PRIVATE_BUCKET = config("B2_MEDIA_PRIVATE_BUCKET", default="starmond-media-private")

B2_CONFIGURED = bool(B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
if B2_CONFIGURED:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": B2_APPLICATION_KEY_ID,
            "secret_key": B2_APPLICATION_KEY,
            "bucket_name": B2_BUCKET_NAME,
            "endpoint_url": B2_ENDPOINT_URL,
            "region_name": B2_REGION,
            "custom_domain": B2_PUBLIC_BASE_URL.replace("https://", "").replace("http://", "") or None,
            "default_acl": None,
            "querystring_auth": False,
        },
    }
    STORAGES["private_media"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": B2_APPLICATION_KEY_ID,
            "secret_key": B2_APPLICATION_KEY,
            "bucket_name": B2_MEDIA_PRIVATE_BUCKET,
            "endpoint_url": B2_ENDPOINT_URL,
            "region_name": B2_REGION,
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 600,  # short-lived authorized URLs
        },
    }
else:
    STORAGES["private_media"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

# Upload limits
MAX_UPLOAD_SIZE_MB = config("MAX_UPLOAD_SIZE_MB", default=8, cast=int)
ALLOWED_IMAGE_MIME_TYPES = ["image/jpeg", "image/png", "image/webp", "image/avif"]
MAX_IMAGE_DIMENSION = 6000

# ---------------------------------------------------------------- Cache / Redis
REDIS_URL = config("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "starmond",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "starmond-dev",
        }
    }
CACHE_TTL_SHORT = config("CACHE_TTL_SHORT", default=60, cast=int)
CACHE_TTL_MEDIUM = config("CACHE_TTL_MEDIUM", default=300, cast=int)
CACHE_TTL_LONG = config("CACHE_TTL_LONG", default=3600, cast=int)

# ---------------------------------------------------------------- Celery
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL or "memory://")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL or "cache+memory://")
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_BEAT_SCHEDULE = {
    "release-expired-inventory-reservations": {
        "task": "apps.inventory.tasks.release_expired_reservations",
        "schedule": 300.0,
    },
    "expire-stale-pending-orders": {
        "task": "apps.orders.tasks.expire_stale_pending_orders",
        "schedule": 600.0,
    },
    "retry-failed-emails": {
        "task": "apps.emails.tasks.retry_failed_emails",
        "schedule": 900.0,
    },
}

# ---------------------------------------------------------------- Email
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="STARMOND TECHNOLOGY LIMITED <no-reply@starmond.example>")
EMAIL_MAX_AUTO_ATTEMPTS = config("EMAIL_MAX_AUTO_ATTEMPTS", default=4, cast=int)

# ---------------------------------------------------------------- Paystack
PAYSTACK_PUBLIC_KEY = config("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_SECRET_KEY = config("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_WEBHOOK_SECRET = config("PAYSTACK_WEBHOOK_SECRET", default="")
PAYSTACK_BASE_URL = "https://api.paystack.co"
PAYSTACK_CURRENCY = config("PAYSTACK_CURRENCY", default="NGN")
PAYSTACK_VERIFY_RETRIES = config("PAYSTACK_VERIFY_RETRIES", default=3, cast=int)

# ---------------------------------------------------------------- Business defaults
DEFAULT_CURRENCY = config("DEFAULT_CURRENCY", default="NGN")
INVENTORY_RESERVATION_MINUTES = config("INVENTORY_RESERVATION_MINUTES", default=30, cast=int)
PENDING_ORDER_EXPIRY_MINUTES = config("PENDING_ORDER_EXPIRY_MINUTES", default=60, cast=int)
MAX_CATEGORY_DEPTH = config("MAX_CATEGORY_DEPTH", default=3, cast=int)
MAX_CART_ITEMS = config("MAX_CART_ITEMS", default=50, cast=int)
MAX_CART_ITEM_QUANTITY = config("MAX_CART_ITEM_QUANTITY", default=100, cast=int)
GUEST_ORDER_LINK_EXPIRY_DAYS = config("GUEST_ORDER_LINK_EXPIRY_DAYS", default=30, cast=int)
REVIEW_COOLDOWN_SECONDS = config("REVIEW_COOLDOWN_SECONDS", default=60, cast=int)

# ---------------------------------------------------------------- Logging
LOG_LEVEL = config("DJANGO_LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": config("DB_LOG_LEVEL", default="WARNING"), "handlers": ["console"], "propagate": False},
        "starmond": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
    },
}