"""
Django settings for reactdjango project.
Template created from AniFight project.
"""

import os
import re
import sys
import logging
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

dotenv_file = os.environ.get("DOTENV_FILE", ".env")
load_dotenv(BASE_DIR / dotenv_file)

ENVIRONMENT = (
    os.environ.get("ENVIRONMENT")
    or os.environ.get("APP_ENV")
    or "development"
).strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"
TESTING = "test" in sys.argv[1:] or bool(os.environ.get("PYTEST_CURRENT_TEST"))

if IS_PRODUCTION and dotenv_file == ".env":
    production_dotenv = BASE_DIR / ".env.production"
    if production_dotenv.exists():
        load_dotenv(production_dotenv, override=True)


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def env_list(name, default=None):
    raw_value = os.environ.get(name)
    values = raw_value.split(",") if raw_value is not None else (default or [])
    return [value.strip() for value in values if value and value.strip()]


def unique_items(values):
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def origin_to_host(value):
    if not value:
        return ""
    parsed = urlparse(value)
    return parsed.hostname or value.split(":")[0].strip("/")


PLACEHOLDER_VALUE_PATTERN = re.compile(
    r"(django-insecure|change|placeholder|example|your[-_ ]?(secret|key)|__required__)",
    re.IGNORECASE,
)
WEAK_PASSWORD_VALUES = {
    "",
    "postgres",
    "password",
    "changeme",
    "secret",
    "__required__",
}


def looks_like_placeholder(value):
    normalized = (value or "").strip()
    return not normalized or bool(PLACEHOLDER_VALUE_PATTERN.search(normalized))


def ensure_strong_secret(name, value, *, min_length=50):
    normalized = (value or "").strip()
    if len(normalized) < min_length or looks_like_placeholder(normalized):
        raise ImproperlyConfigured(
            f"{name} must be set to a strong random value in production."
        )


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-CHANGE-THIS-IN-PRODUCTION"
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool("DEBUG", not IS_PRODUCTION)

APP_ORIGIN = os.environ.get("APP_ORIGIN", "").rstrip("/")
API_ORIGIN = os.environ.get("API_ORIGIN", "").rstrip("/")

PUBLIC_APP_URL = os.environ.get("PUBLIC_APP_URL", APP_ORIGIN).rstrip("/")
API_BASE_URL = os.environ.get(
    "API_BASE_URL",
    (
        f"{API_ORIGIN}/api"
        if API_ORIGIN
        else (f"{PUBLIC_APP_URL}/api" if PUBLIC_APP_URL else "")
    ),
).rstrip("/")

default_allowed_hosts = [
    host
    for host in {
        origin_to_host(APP_ORIGIN),
        origin_to_host(API_ORIGIN),
        origin_to_host(PUBLIC_APP_URL),
        origin_to_host(API_BASE_URL),
    }
    if host
]
if DEBUG:
    default_allowed_hosts.extend(["localhost", "127.0.0.1"])

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS", default_allowed_hosts or ["localhost", "127.0.0.1"]
)

default_dev_frontend_origins = (
    ["http://localhost:3000", "http://127.0.0.1:3000"] if DEBUG else []
)
default_dev_backend_origins = (
    ["http://localhost:8000", "http://127.0.0.1:8000"] if DEBUG else []
)
default_social_frontend_origins = unique_items(
    [origin for origin in [APP_ORIGIN, PUBLIC_APP_URL] if origin]
    + default_dev_frontend_origins
)

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party apps
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "channels",
    # Local apps
    "accounts",
    "subscriptions",
    "workspace.apps.WorkspaceConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "clausechain.middleware.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "clausechain.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "clausechain.wsgi.application"
ASGI_APPLICATION = "clausechain.asgi.application"

# Database
db_engine = os.environ.get("DB_ENGINE", "django.db.backends.postgresql")

if db_engine == "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": db_engine,
            "NAME": os.environ.get("DB_NAME", BASE_DIR / "db.sqlite3"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": db_engine,
            "NAME": os.environ.get("DB_NAME", "reactdjango_db"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# ClauseChain engine integration.  The backend treats these artifacts as the
# authoritative review state and never imports engine modules into the Django
# process.  Production points ENGINE_ROOT at the separately deployed engine.
ENGINE_ROOT = Path(os.environ.get("ENGINE_ROOT", BASE_DIR.parent / "engine")).resolve()
ENGINE_PYTHON = os.environ.get(
    "ENGINE_PYTHON",
    str(ENGINE_ROOT / ".venv" / "bin" / "python"),
)
WORKSPACE_DECISION_WRITER = os.environ.get(
    "WORKSPACE_DECISION_WRITER",
    str(ENGINE_ROOT / "scripts" / "apply_decisions.py"),
)
WORKSPACE_LOCK_DIR = Path(
    os.environ.get("WORKSPACE_LOCK_DIR", BASE_DIR / "var" / "locks")
).resolve()
ENGINE_ALLOWLIST = Path(
    os.environ.get("ENGINE_ALLOWLIST", BASE_DIR.parent / "deploy" / "engine_allowlist.json")
).resolve()

# Simple JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get(
        "JWT_SIGNING_KEY",
        SECRET_KEY if not IS_PRODUCTION else "",
    ).strip(),
    "VERIFYING_KEY": None,
    "AUDIENCE": None,
    "ISSUER": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
}

# CORS Settings
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    unique_items(
        [origin for origin in [APP_ORIGIN, PUBLIC_APP_URL] if origin]
        + default_dev_frontend_origins
    ),
)

CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    unique_items(
        [origin for origin in [APP_ORIGIN, API_ORIGIN, PUBLIC_APP_URL] if origin]
        + default_dev_frontend_origins
        + default_dev_backend_origins
    ),
)

USE_REDIS = env_bool("USE_REDIS", IS_PRODUCTION and not TESTING)
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_CACHE_LOCATION = os.environ.get(
    "REDIS_CACHE_LOCATION",
    f"redis://{REDIS_HOST}:{REDIS_PORT}/1",
)

# Channels
if USE_REDIS:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [(REDIS_HOST, REDIS_PORT)],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# Cache
if USE_REDIS:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_CACHE_LOCATION,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "reactdjango-local-cache",
        }
    }

# Email
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@example.com")

# Celery
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/2")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = env_bool("CELERY_TASK_EAGER_PROPAGATES", True)
CELERY_BEAT_SCHEDULE = {
    "subscriptions-check-expiring-subscriptions": {
        "task": "subscriptions.tasks.check_expiring_subscriptions",
        "schedule": crontab(hour=2, minute=0),
    },
    "subscriptions-check-expired-subscriptions": {
        "task": "subscriptions.tasks.check_expired_subscriptions",
        "schedule": crontab(hour=3, minute=0),
    },
    "subscriptions-expire-stale-bkash-transactions": {
        "task": "subscriptions.tasks.expire_stale_bkash_transactions",
        "schedule": crontab(minute=15),
    },
}

USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
SESSION_COOKIE_HTTPONLY = True

AUTH_REFRESH_COOKIE_NAME = os.environ.get("AUTH_REFRESH_COOKIE_NAME", "reactdjango_refresh")
AUTH_REFRESH_COOKIE_PATH = os.environ.get("AUTH_REFRESH_COOKIE_PATH", "/api/auth/")
AUTH_REFRESH_COOKIE_SECURE = env_bool("AUTH_REFRESH_COOKIE_SECURE", IS_PRODUCTION)
AUTH_REFRESH_COOKIE_SAMESITE = os.environ.get("AUTH_REFRESH_COOKIE_SAMESITE", "Strict")
AUTH_REFRESH_COOKIE_DOMAIN = os.environ.get("AUTH_REFRESH_COOKIE_DOMAIN", "").strip()
SOCIAL_AUTH_ALLOWED_FRONTEND_ORIGINS = env_list(
    "SOCIAL_AUTH_ALLOWED_FRONTEND_ORIGINS",
    default_social_frontend_origins,
)
SOCIAL_AUTH_FRONTEND_CALLBACK_PATH = os.environ.get(
    "SOCIAL_AUTH_FRONTEND_CALLBACK_PATH",
    "/auth/social/callback",
).strip() or "/auth/social/callback"
TRUSTED_PROXY_IPS = env_list("TRUSTED_PROXY_IPS", [])
SIGNUP_CAPTCHA_TTL_SECONDS = int(os.environ.get("SIGNUP_CAPTCHA_TTL_SECONDS", "600"))
SIGNUP_FORM_MIN_AGE_SECONDS = int(os.environ.get("SIGNUP_FORM_MIN_AGE_SECONDS", "3"))
SIGNUP_FORM_MAX_AGE_SECONDS = int(os.environ.get("SIGNUP_FORM_MAX_AGE_SECONDS", "3600"))
SIGNUP_DISPOSABLE_EMAIL_BLOCKLIST = env_list("SIGNUP_DISPOSABLE_EMAIL_BLOCKLIST", [])
SIGNUP_DISPOSABLE_EMAIL_ALLOWLIST = env_list("SIGNUP_DISPOSABLE_EMAIL_ALLOWLIST", [])
BKASH_CALLBACK_TRUSTED_IPS = env_list("BKASH_CALLBACK_TRUSTED_IPS", [])
BKASH_WEBHOOK_TOPIC_ARN = os.environ.get("BKASH_WEBHOOK_TOPIC_ARN", "").strip()
BKASH_WEBHOOK_URL = os.environ.get("BKASH_WEBHOOK_URL", "").strip()
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: https:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
    ]
)

if IS_PRODUCTION:
    ensure_strong_secret("DJANGO_SECRET_KEY", SECRET_KEY)
    ensure_strong_secret("JWT_SIGNING_KEY", SIMPLE_JWT["SIGNING_KEY"])
    if SIMPLE_JWT["SIGNING_KEY"] == SECRET_KEY:
        raise ImproperlyConfigured(
            "JWT_SIGNING_KEY must be set separately from DJANGO_SECRET_KEY in production."
        )
    if (
        db_engine != "django.db.backends.sqlite3"
        and os.environ.get("DB_PASSWORD", "").strip().lower() in WEAK_PASSWORD_VALUES
    ):
        raise ImproperlyConfigured(
            "DB_PASSWORD must be set to a strong value in production."
        )
    if DEBUG:
        raise ImproperlyConfigured("DEBUG must be False in production.")
    if env_bool("TRUST_X_FORWARDED_PROTO", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        False,
    )
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
    SECURE_REFERRER_POLICY = os.environ.get(
        "SECURE_REFERRER_POLICY",
        "strict-origin-when-cross-origin",
    )
    SECURE_CONTENT_TYPE_NOSNIFF = env_bool("SECURE_CONTENT_TYPE_NOSNIFF", True)
    X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")
else:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        False,
    )
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
    SECURE_REFERRER_POLICY = os.environ.get(
        "SECURE_REFERRER_POLICY",
        "strict-origin-when-cross-origin",
    )
    SECURE_CONTENT_TYPE_NOSNIFF = env_bool("SECURE_CONTENT_TYPE_NOSNIFF", True)
    X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

if IS_PRODUCTION and (
    not USE_REDIS
    or CACHES["default"]["BACKEND"] != "django.core.cache.backends.redis.RedisCache"
):
    logger.warning(
        "Production rate limiting requires USE_REDIS=true with django.core.cache.backends.redis.RedisCache. "
        "Current cache backend: %s",
        CACHES["default"]["BACKEND"],
    )

# Stripe
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Social auth
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
FACEBOOK_OAUTH_CLIENT_ID = os.environ.get("FACEBOOK_OAUTH_CLIENT_ID", "").strip()
FACEBOOK_OAUTH_CLIENT_SECRET = os.environ.get(
    "FACEBOOK_OAUTH_CLIENT_SECRET",
    "",
).strip()
FACEBOOK_GRAPH_API_VERSION = os.environ.get(
    "FACEBOOK_GRAPH_API_VERSION",
    "v25.0",
).strip() or "v25.0"
GITHUB_OAUTH_CLIENT_ID = os.environ.get("GITHUB_OAUTH_CLIENT_ID", "").strip()
GITHUB_OAUTH_CLIENT_SECRET = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "").strip()

# bKash
BKASH_APP_KEY = os.environ.get("BKASH_APP_KEY", "")
BKASH_APP_SECRET = os.environ.get("BKASH_APP_SECRET", "")
BKASH_USERNAME = os.environ.get("BKASH_USERNAME", "")
BKASH_PASSWORD = os.environ.get("BKASH_PASSWORD", "")
BKASH_BASE_URL = os.environ.get(
    "BKASH_BASE_URL",
    "https://tokenized.sandbox.bka.sh/v1.2.0-beta",
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
AUDIT_LOG_LEVEL = os.environ.get("AUDIT_LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "audit": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "audit_console": {
            "class": "logging.StreamHandler",
            "formatter": "audit",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "audit": {
            "handlers": ["audit_console"],
            "level": AUDIT_LOG_LEVEL,
            "propagate": False,
        },
    },
}
