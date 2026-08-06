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
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="http://localhost:8000,http://127.0.0.1:8000", cast=Csv())

# ── Production security (disabled in DEBUG) ────────────────────────────
if not DEBUG:
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
    "ops",
    "partners",
    "dashboard",
    "automation",
    "django_extensions",
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
# PostgreSQL from day one (falls back to SQLite for local dev without DATABASE_URL)
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

# ── Static files ──────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ── Default primary key field ─────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Session (identity picker) ─────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 86400 * 30  # 30 days
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ── Admin shared password ─────────────────────────────────────────────
ADMIN_SHARED_PASSWORD = config("ADMIN_SHARED_PASSWORD", default="aiesec-carthage-admin")

# ── Celery (Upstash Redis — free 256 MB) ───────────────────────────
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_TIMEZONE = "Africa/Tunis"
CELERY_TASK_TRACK_STARTED = True
# SSL for Upstash (rediss:// handled automatically by Celery)
CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": "CERT_NONE"}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CELERY_BROKER_URL,
    }
}

# ── File uploads ──────────────────────────────────────────────────────
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ── Email ──────────────────────────────────────────────────────────────
# Default: SMTP via Brevo (free tier — 300 emails/day).
# Falls back to console backend if no SMTP credentials are set.
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="smtp-relay.brevo.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@aiesec-carthage.org")

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
