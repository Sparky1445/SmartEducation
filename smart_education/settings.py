"""
Django settings for the Smart Education project (INT253).

Secrets and switches come from a .env file next to manage.py
(copy .env.example to .env). Real environment variables always win.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- Core -------------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # --- Atharwa ---
    "core",
    "ai_engine",  # internal only: no public pages
    "ask",
    "outreach_studio",
    "engagement",
    "dashboard",
    "repository",
    "accounts",
    "media_portal",
    "courses",
    # "media_portal",
    # "courses",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "smart_education.urls"

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
                "core.context_processors.preferences",
                "media_portal.context_processors.announcements",
            ],
        },
    },
]

WSGI_APPLICATION = "smart_education.wsgi.application"

# --- Database (Unit V: database configuration) -----------------------------
# SQLite by default. Set DB_ENGINE=postgres in .env for the final demo.
if os.getenv("DB_ENGINE", "sqlite").lower() == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "smart_education"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static and media --------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# PDFs open inside the lesson page (same site only).
X_FRAME_OPTIONS = "SAMEORIGIN"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "home"

# --- AI engine (Atharwa) -----------------------------------------------------
# LLM_PROVIDER: MOCK | GITHUB_MODELS | AZURE  (same names as PackPilot's .env)
# A provider without its key silently falls back to MOCK, so the site always runs.
AI_ENGINE = {
    "PROVIDER": os.getenv("LLM_PROVIDER", "MOCK").upper(),
    "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", ""),
    "GITHUB_MODEL": os.getenv("GITHUB_MODEL", "openai/gpt-4o-mini"),
    "AZURE_ENDPOINT": os.getenv("AZURE_INFERENCE_ENDPOINT", ""),
    "AZURE_KEY": os.getenv("AZURE_INFERENCE_KEY", ""),
    "AZURE_MODEL": os.getenv("AZURE_MODEL", "gpt-4o-mini"),
    "AZURE_API_VERSION": os.getenv("AZURE_API_VERSION", "2024-10-21"),
    "TIMEOUT_SECONDS": int(os.getenv("AI_TIMEOUT_SECONDS", "45")),
}

# Answers whose source match is below this are replaced by "not in the repository".
ASK_TRUST_THRESHOLD = int(os.getenv("ASK_TRUST_THRESHOLD", "55"))
# When the repository has no answer, the LLM gives a general answer (clearly labelled).
ASK_GENERAL_FALLBACK = env_bool("ASK_GENERAL_FALLBACK", True)

# Related videos and websites under every answer. Both keys are optional:
# without them the page shows Wikipedia articles and search links.
WEB_LINKS = {
    "YOUTUBE_API_KEY": os.getenv("YOUTUBE_API_KEY", ""),
    "BRAVE_API_KEY": os.getenv("BRAVE_API_KEY", ""),
    "CACHE_HOURS": int(os.getenv("WEB_LINKS_CACHE_HOURS", "24")),
    "OFFLINE": env_bool("WEB_LINKS_OFFLINE", False),
}

# Outreach kits are made in a background thread; tests set this True to run inline.
OUTREACH_RUN_INLINE = False

# --- Logging (Unit III: debugging) -------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name} :: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "agent_file": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "agent_runs.log",
            "formatter": "plain",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "ai_engine": {"handlers": ["console", "agent_file"], "level": "INFO", "propagate": False},
    },
}

# Uploads above this size are streamed to a temp file instead of memory.
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024

# Password reset emails: printed to the terminal in development. Set EMAIL_* in .env for real mail.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Smart Education <no-reply@smarteducation.local>")
