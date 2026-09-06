"""
Django settings for AIESEC LC Carthage EP/IR Centralization Tool.
"""
import os
from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ──────────────────────────────────────────────────────────
SECRET_KEY = config("SECRET_KEY", default="dev-secret-key-change-in-production")
DEBUG = config("DEBUG", default=True, cast=bool)

ALLOWED_HOSTS = list(
    config("ALLOWED_HOSTS", default="localhost,127.0.0.1,.onrender.com", cast=Csv())
)
CSRF_TRUSTED_ORIGINS = list(
    config(
        "CSRF_TRUSTED_ORIGINS",
        default="http://localhost:8000,http://127.0.0.1:8000",
        cast=Csv(),
    )
)

# Render injects the public hostname at runtime
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)

# ── Production security (disabled in DEBUG) ────────────────────────────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ── Applications ──────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Local apps
    "core",
    "members",
    "ops.apps.OpsConfig",
    "partners",
    "dashboard",
    "automation",
    "cloudinary",
    "cloudinary_storage",
]

# Dev-only apps (optional — not required on Render)
if DEBUG:
    try:
        import django_extensions  # noqa: F401
        INSTALLED_APPS += ["django_extensions"]
    except ImportError:
        pass

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom member middleware (links auth.User to Member profile)
    "members.middleware.CurrentMemberMiddleware",
    "members.middleware.RequireLoginMiddleware",
]

LOGIN_URL = "/members/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/members/login/"

ROOT_URLCONF = "aiesec_tool.urls"

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
                "members.context_processors.identity",
            ],
        },
    },
]

WSGI_APPLICATION = "aiesec_tool.wsgi.application"

# ── Database ───────────────────────────────────────────────────────────
# PostgreSQL (Supabase) via DATABASE_URL; SQLite fallback for local dev
DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=0)}
    DATABASES["default"]["OPTIONS"] = {
        "sslmode": "require",
        "connect_timeout": 10,
    }
    CONN_HEALTH_CHECKS = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ── Auth (not used — session-based identity only) ─────────────────────
AUTH_PASSWORD_VALIDATORS = []

# ── Internationalization ──────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True

# ── Static files (WhiteNoise) ─────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── Media (Cloudinary in production, filesystem locally) ──────────────
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
CLOUDINARY_URL = config("CLOUDINARY_URL", default="")

if CLOUDINARY_URL and not DEBUG:
    import cloudinary
    import cloudinary.uploader  # noqa: F401
    import cloudinary.api  # noqa: F401

    cloudinary.config(cloudinary_url=CLOUDINARY_URL)
    STORAGES = {
        "default": {
            "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# ── Default primary key field ─────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Session ───────────────────────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 86400 * 30  # 30 days
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ── Admin shared password ─────────────────────────────────────────────
ADMIN_SHARED_PASSWORD = config("ADMIN_SHARED_PASSWORD", default="aiesec-carthage-admin")

# ── Cron (cron-job.org → /api/cron/<task>/) ───────────────────────────
CRON_SECRET = os.environ.get("CRON_SECRET", "change-me-in-production")

# ── Celery (optional — off on Render free tier) ───────────────────────
USE_CELERY = os.environ.get("USE_CELERY", "False") == "True"

if USE_CELERY:
    CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
    CELERY_TIMEZONE = "Africa/Tunis"
    CELERY_TASK_TRACK_STARTED = True
    if str(CELERY_BROKER_URL).startswith("rediss://"):
        CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": "CERT_NONE"}
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CELERY_BROKER_URL,
        }
    }
else:
    CELERY_BROKER_URL = None
    CELERY_RESULT_BACKEND = None
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "aiesec-tool",
        }
    }

# ── Email ──────────────────────────────────────────────────────────────
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@localhost")

# ── AIESEC LC Carthage config (overridable via SiteConfig model) ──────
LC_NAME = "AIESEC LC Carthage"
CURRENT_TERM = "2026-S1"
STAGE_IDLE_THRESHOLDS = {
    "open": 14,
    "matched_with_opp": 7,
    "applied": 7,
    "accepted": 14,
    "approved": 14,
    "all_papers_done": 7,
    "not_all_papers_done": 7,
    "do_papers": 14,
}
