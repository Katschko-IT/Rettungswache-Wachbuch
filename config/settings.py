import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent

from core.version import APP_VERSION as DEFAULT_APP_VERSION  # noqa: E402


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


configured_secret = os.getenv("DJANGO_SECRET_KEY") or os.getenv("SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG")
if not configured_secret and not DEBUG:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DEBUG is false.")
SECRET_KEY = configured_secret or "development-only-rwsth-4Jt8vR2mQ7xN5kP9sW3cL6hF1yD0aB"
ALLOWED_HOSTS = [value.strip() for value in os.getenv(
    "ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
).split(",") if value.strip()]
CSRF_TRUSTED_ORIGINS = [value.strip() for value in os.getenv(
    "CSRF_TRUSTED_ORIGINS", ""
).split(",") if value.strip()]

INSTALLED_APPS = [
    "axes",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CorrelationIdMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "core.middleware.ClientIPMiddleware",
    "axes.middleware.AxesMiddleware",
    # Innermost guard: blocks demo-forbidden routes (by URL name) only when
    # DEMO_PUBLIC_MODE is enabled. Harmless in normal operation.
    "core.middleware.PublicDemoGuardMiddleware",
]

# Optional Redis cache. Keep serialized values non-executable: django-redis uses
# pickle by default, so Wachbuch selects the built-in JSON serializer instead.
REDIS_URL = os.getenv("REDIS_URL", "").strip()
REDIS_HOST = os.getenv("REDIS_HOST", "").strip()
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "").strip()

# REDIS_URL is the single source of truth. The discrete REDIS_HOST/PORT/DB/
# PASSWORD variables are only a local-development fallback. With no Redis
# configured the site uses the process-local locmem cache and database-backed
# sessions instead of being forced onto Redis.
if not REDIS_URL and REDIS_HOST:
    _redis_port = os.getenv("REDIS_PORT", "6379").strip() or "6379"
    _redis_db = os.getenv("REDIS_DB", "0").strip() or "0"
    _redis_auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
    REDIS_URL = f"redis://{_redis_auth}{REDIS_HOST}:{_redis_port}/{_redis_db}"

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "SERIALIZER": "django_redis.serializers.json.JSONSerializer",
                "SOCKET_CONNECT_TIMEOUT": 3,
                "SOCKET_TIMEOUT": 3,
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": 100,
                    "retry_on_timeout": True,
                },
                "REDIS_CLIENT_KWARGS": {
                    "health_check_interval": 30,
                },
            },
            "KEY_PREFIX": "wachbuch",
            "TIMEOUT": 300,
        }
    }

    # cached_db keeps the database as the durable session source of truth while
    # Redis accelerates reads. Redis loss therefore does not become session loss.
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
    SESSION_CACHE_ALIAS = "default"

    CACHE_TIMEOUTS = {
        "handovers_list": 60,
        "calendar_events": 120,
        "station_tasks": 300,
        "dashboard": 30,
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "wachbuch-locmem",
            "TIMEOUT": 300,
        }
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Strukturierte Logs: Korrelations-ID ohne personenbezogene Nutzdaten.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "wachbuch.errors": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "wachbuch.requests": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_HTTP_RESPONSE_CODE = 429
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context.current_membership",
                "core.context.application_metadata",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
if os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(conn_max_age=60, conn_health_checks=True)
    }
elif os.getenv("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ["DB_HOST"],
            "PORT": os.getenv("DB_PORT", "5432"),
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ["DB_USER"],
            "PASSWORD": os.environ["DB_PASSWORD"],
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": dj_database_url.parse(f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# BSI TR-02102 / moderne Verwaltungspraxis: Argon2id bevorzugt, PBKDF2 als Fallback.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Defect photos are transported as base64 inside JSON. A 2 MiB binary image
# expands to roughly 2.67 MiB before the small JSON envelope is added, so the
# request-body ceiling must sit above the binary domain limit.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE", str(3 * 1024 * 1024))
)

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "landing"
LOGOUT_REDIRECT_URL = "landing"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
SECURE_COOKIES = env_bool("SECURE_COOKIES", default=not DEBUG)
SESSION_COOKIE_SECURE = SECURE_COOKIES
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"

# TLS terminates at an external reverse proxy. Inside the container the health
# probe and Gunicorn speak plain HTTP on loopback, so Django must not redirect.
SECURE_SSL_REDIRECT = False
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W008", "security.W021"]

DEFAULT_STATION_NAME = os.getenv("DEFAULT_STATION_NAME", "Rettungswache").strip()
DEFAULT_STATION_SLUG = os.getenv("DEFAULT_STATION_SLUG", "rettungswache").strip()
APP_NAME = os.getenv("APP_NAME", "Wachwerk").strip() or "Wachwerk"
SOURCE_URL = os.getenv(
    "SOURCE_URL", "https://github.com/Darkspike1988/Rettungswache-Wachbuch"
).strip()
APP_VERSION = os.getenv("APP_VERSION", DEFAULT_APP_VERSION).strip()
FEED_ALLOWED_HOSTS = {
    value.strip().lower()
    for value in os.getenv("FEED_ALLOWED_HOSTS", "").split(",")
    if value.strip()
}
FEED_MAX_BYTES = 2_000_000
WASTE_CALENDAR_MAX_BYTES = 1_048_576
RETENTION_FEED_DAYS = int(os.getenv("RETENTION_FEED_DAYS", "90") or "0")
RETENTION_AUDIT_DAYS = int(os.getenv("RETENTION_AUDIT_DAYS", "0") or "0")
MFA_ENABLED = env_bool("MFA_ENABLED", default=True)
MFA_REQUIRED = env_bool("MFA_REQUIRED", default=False)
DEMO_MODE = env_bool("DEMO_MODE", default=False)
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "Demo-Passwort-12345").strip() or "Demo-Passwort-12345"
if DEMO_MODE:
    # Presentations should not require MFA setup on every demo account.
    MFA_REQUIRED = False
REGISTRATION_ENABLED = env_bool("REGISTRATION_ENABLED", default=False)
REGISTRATION_RATE_LIMIT = int(os.getenv("REGISTRATION_RATE_LIMIT", "5") or "5")
TRUSTED_PROXY = env_bool("TRUSTED_PROXY", default=False)
RATELIMIT_KEY_SALT = os.getenv("RATELIMIT_KEY_SALT", "wachbuch")
WEBAUTHN_ENABLED = env_bool("WEBAUTHN_ENABLED", default=True)
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", "").strip()
WEBAUTHN_ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "").strip()
WEB_PUSH_ENABLED = env_bool("WEB_PUSH_ENABLED", default=False)
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_ADMIN_EMAIL = os.getenv("VAPID_ADMIN_EMAIL", "ops@localhost").strip() or "ops@localhost"
# HTTPS host allowlist for browser push subscription endpoints (SSRF guard).
# The same list feeds CSP ``connect-src`` (no scheme-wide ``https:``).
# Entries match an exact host; entries starting with "." match that suffix
# (subdomains included). Override via PUSH_ALLOWED_ENDPOINT_HOSTS; an empty
# value keeps the built-in list of known browser push services.
PUSH_ALLOWED_ENDPOINT_HOSTS = {
    value.strip().lower()
    for value in (
        os.getenv("PUSH_ALLOWED_ENDPOINT_HOSTS", "").strip()
        or "fcm.googleapis.com,push.googleapis.com,updates.push.services.mozilla.com,"
        ".push.apple.com,.notify.windows.com,.notify.live.net"
    ).split(",")
    if value.strip()
}

# Essential auth cookies only. No analytics or advertising cookies are set.
SESSION_COOKIE_NAME = "rwsth_session"
CSRF_COOKIE_NAME = "rwsth_csrf"
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = False

# Use cached template loader for production.
# APP_DIRS and loaders are mutually exclusive; keep app_dirs semantics by
# listing the appDirectories loader explicitly alongside the filesystem loader.
if not DEBUG:
    TEMPLATES[0]["OPTIONS"]["loaders"] = [
        (
            "django.template.loaders.cached.Loader",
            [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        ),
    ]
    TEMPLATES[0].pop("APP_DIRS", None)
# Public, internet-facing demonstration instance. This is a superset of
# DEMO_MODE with hard, non-optional guards so visitors can only ever see
# fictional data and can never reach production-style operations (user
# creation, token/passkey enrolment, push/feed egress, Django admin or
# station configuration). Normal (non-demo) operation is untouched.
DEMO_PUBLIC_MODE = env_bool("DEMO_PUBLIC_MODE", default=False)
if DEMO_PUBLIC_MODE:
    # Always behave like a demo instance: seed data, banner, one-click login.
    DEMO_MODE = True
    # No self-service sign-ups on a public instance.
    REGISTRATION_ENABLED = False
    # No outbound push/feed egress: keep both switches and their secrets empty
    # so the worker has nothing to contact even if it is scheduled.
    WEB_PUSH_ENABLED = False
    VAPID_PUBLIC_KEY = ""
    VAPID_PRIVATE_KEY = ""
    FEED_ALLOWED_HOSTS = set()
    # Shared demo accounts must not be forced through MFA enrolment.
    MFA_REQUIRED = False
