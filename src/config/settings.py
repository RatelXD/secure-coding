"""Django settings with explicit development and fail-closed production modes."""

import os
from ipaddress import ip_address
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]


def _boolean(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean")


def _csv(name: str, *, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} is required")
    return value


APP_ENV = os.getenv("APP_ENV", "production").strip().lower()
if APP_ENV not in {"development", "test", "production"}:
    raise ImproperlyConfigured("APP_ENV must be development, test, or production")

IS_PRODUCTION = APP_ENV == "production"
DEBUG = _boolean("DJANGO_DEBUG", default=False)
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured("DJANGO_DEBUG cannot be enabled in production")

if IS_PRODUCTION:
    SECRET_KEY = _required("DJANGO_SECRET_KEY")
    if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("development-"):
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is not suitable for production")
    ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured("production requires explicit DJANGO_ALLOWED_HOSTS")
else:
    SECRET_KEY = os.getenv(
        "DJANGO_SECRET_KEY",
        "development-only-change-me-before-any-shared-deployment-000000",
    )
    ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1")

CSRF_TRUSTED_ORIGINS = _csv("DJANGO_CSRF_TRUSTED_ORIGINS")
if IS_PRODUCTION and not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("production requires explicit DJANGO_CSRF_TRUSTED_ORIGINS")
if any(not origin.startswith(("http://", "https://")) for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS entries must include a scheme")
if IS_PRODUCTION and any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("production CSRF trusted origins must use HTTPS")

TRUST_PROXY_HEADERS = _boolean("DJANGO_TRUST_PROXY_HEADERS", default=False)
TRUSTED_PROXY_IPS = frozenset(_csv("DJANGO_TRUSTED_PROXY_IPS"))
USE_X_FORWARDED_HOST = False
if TRUST_PROXY_HEADERS:
    if not TRUSTED_PROXY_IPS:
        raise ImproperlyConfigured(
            "DJANGO_TRUSTED_PROXY_IPS is required when proxy headers are trusted"
        )
    try:
        TRUSTED_PROXY_IPS = frozenset(str(ip_address(value)) for value in TRUSTED_PROXY_IPS)
    except ValueError as exc:
        raise ImproperlyConfigured("DJANGO_TRUSTED_PROXY_IPS must contain IP literals") from exc
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "apps.accounts",
    "apps.catalog",
    "apps.chat",
    "apps.moderation",
]

MIDDLEWARE = [
    "config.middleware.TrustedProxyHeadersMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.middleware.CanonicalUserStatusMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
AUTH_USER_MODEL = "accounts.User"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "src" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

POSTGRES_SSLMODE = os.getenv(
    "POSTGRES_SSLMODE",
    "require" if IS_PRODUCTION else "disable",
).strip().lower()
_VALID_POSTGRES_SSLMODES = frozenset(
    {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
)
if POSTGRES_SSLMODE not in _VALID_POSTGRES_SSLMODES:
    raise ImproperlyConfigured("POSTGRES_SSLMODE is not a valid libpq TLS mode")
if IS_PRODUCTION and POSTGRES_SSLMODE not in {"require", "verify-ca", "verify-full"}:
    raise ImproperlyConfigured("production POSTGRES_SSLMODE must require TLS")


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _required("POSTGRES_DB"),
        "USER": _required("POSTGRES_USER"),
        "PASSWORD": _required("POSTGRES_PASSWORD"),
        "HOST": _required("POSTGRES_HOST"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "sslmode": POSTGRES_SSLMODE,
            "connect_timeout": 2,
            "tcp_user_timeout": 2_000,
        },
    }
}

REDIS_URL = os.getenv("REDIS_URL", "" if IS_PRODUCTION else "redis://127.0.0.1:6379/0")
if not REDIS_URL:
    raise ImproperlyConfigured("REDIS_URL is required")
if IS_PRODUCTION and not REDIS_URL.startswith("rediss://"):
    raise ImproperlyConfigured("production REDIS_URL must use TLS (rediss://)")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "prefix": "marketplace",
            "expiry": 60,
            "group_expiry": 300,
            "capacity": 100,
            "symmetric_encryption_keys": [SECRET_KEY],
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "apps.accounts.validators.PasswordBoundsValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.ScryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "src" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = IS_PRODUCTION
SECURE_SSL_REDIRECT = IS_PRODUCTION
SECURE_HSTS_SECONDS = 31_536_000 if IS_PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = IS_PRODUCTION
SECURE_HSTS_PRELOAD = IS_PRODUCTION
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}
