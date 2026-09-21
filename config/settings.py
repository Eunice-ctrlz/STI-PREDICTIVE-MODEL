from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "sti-frontend"

load_dotenv(BASE_DIR / ".env")

# Local Windows GeoDjango support. Production uses PostGIS.
if os.name == "nt":
    OSGEO4W = r"C:\OSGeo4W"
    os.environ["OSGEO4W_ROOT"] = OSGEO4W
    os.environ["GDAL_DATA"] = OSGEO4W + r"\share\gdal"
    os.environ["PROJ_LIB"] = OSGEO4W + r"\share\proj"
    os.environ["PATH"] = OSGEO4W + r"\bin;" + os.environ["PATH"]
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(OSGEO4W + r"\bin")
    GDAL_LIBRARY_PATH = OSGEO4W + r"\bin\gdal313.dll"
    GEOS_LIBRARY_PATH = OSGEO4W + r"\bin\geos_c.dll"
    SPATIALITE_LIBRARY_PATH = OSGEO4W + r"\bin\mod_spatialite.dll"
    from ctypes import CDLL
    CDLL(GDAL_LIBRARY_PATH)

SECRET_KEY = os.environ.get("SECRET_KEY", "").strip() or "dev-only-insecure-key-change-me"
DEBUG = os.environ.get("DEBUG", "True").strip().lower() in ("1", "true", "yes", "on")

allowed_hosts = os.environ.get("ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts.split(",") if h.strip()]
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "ninja",
    "corsheaders",
    "rest_framework",
    "patients",
    "prediction_engine",
    "clinicians",
    "geospatial",
    "moh_reporting",
    "compliance",
    "data_ingestion",
    "preprocessing",
    "ml_pipeline",
    "ai_service",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "compliance.middleware.AuditLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [FRONTEND_DIR],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
    # GeoDjango needs the PostGIS backend when the production DB contains
    # PointField/PolygonField columns.
    DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.spatialite",
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
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Render/proxy security. Safe for local development and enabled in production.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


def _env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# Optional AI explanation layer. Disabled by default for the first deployment.
AI_EXPLANATIONS_ENABLED = _env_bool("AI_EXPLANATIONS_ENABLED", False)
AI_PROVIDER = os.environ.get("AI_PROVIDER", "ollama").strip() or "ollama"
AI_MODEL = os.environ.get("AI_MODEL", "llama3.2:3b").strip() or "llama3.2:3b"
AI_MAX_TOKENS = _env_int("AI_MAX_TOKENS", 2000)
AI_TIMEOUT_SECONDS = _env_int("AI_TIMEOUT_SECONDS", 30)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
AI_BASE_URL = os.environ.get("AI_BASE_URL", "").strip()

# RAG is also deferred until the core API is stable.
RAG_ENABLED = _env_bool("RAG_ENABLED", False)
RAG_CHROMA_PATH = os.environ.get("RAG_CHROMA_PATH", "").strip()
RAG_COLLECTION_NAME = os.environ.get("RAG_COLLECTION_NAME", "sti_knowledge").strip()
RAG_EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()
RAG_CHUNK_SIZE = _env_int("RAG_CHUNK_SIZE", 500)
RAG_CHUNK_OVERLAP = _env_int("RAG_CHUNK_OVERLAP", 100)
RAG_TOP_K = _env_int("RAG_TOP_K", 3)
try:
    RAG_MIN_SCORE = float(os.environ.get("RAG_MIN_SCORE", "0.35") or 0.35)
except ValueError:
    RAG_MIN_SCORE = 0.35
