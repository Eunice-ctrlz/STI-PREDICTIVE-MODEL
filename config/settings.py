
from pathlib import Path

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / 'frontend'

# Load .env before anything below reads os.environ. Absent file is not an
# error: every .env-backed setting has a safe default, and the ML prediction
# path does not depend on any of them.
from dotenv import load_dotenv

load_dotenv(BASE_DIR / '.env')

if os.name == "nt":
    OSGEO4W = r"C:\OSGeo4W"
    os.environ["OSGEO4W_ROOT"] = OSGEO4W
    os.environ["GDAL_DATA"] = OSGEO4W + r"\share\gdal"
    os.environ["PROJ_LIB"] = OSGEO4W + r"\share\proj"
    os.environ["PATH"] = OSGEO4W + r"\bin;" + os.environ["PATH"]

    # Required on Python 3.8+ — PATH alone doesn't let ctypes resolve
    # a DLL's own dependencies, so we register the dir explicitly
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(OSGEO4W + r"\bin")

    GDAL_LIBRARY_PATH = OSGEO4W + r"\bin\gdal313.dll"
    GEOS_LIBRARY_PATH = OSGEO4W + r"\bin\geos_c.dll"
    SPATIALITE_LIBRARY_PATH = OSGEO4W + r"\bin\mod_spatialite.dll"

    # Force-load GDAL before anything else can grab conflicting DLLs. This
    # lives here rather than only in manage.py so that wsgi/asgi entrypoints
    # (and any bare `django.setup()`) get it too — without it they fail with
    # "WinError 127: The specified procedure could not be found".
    from ctypes import CDLL

    CDLL(GDAL_LIBRARY_PATH)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-3-pdw6z-q=*(yd&e)30e266fvq6=%0pc&wc%m-etq^q=+gj5q2'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',

    'ninja',
    'corsheaders',
    'rest_framework',

    'patients',
    'prediction_engine',
    'clinicians',
    'geospatial',
    'moh_reporting',
    'compliance',
    'data_ingestion',
    'preprocessing',
    'ml_pipeline',
    'ai_service',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Records every API request into compliance.AuditLog. Must run after
    # AuthenticationMiddleware so request.user is resolved.
    'compliance.middleware.AuditLogMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [FRONTEND_DIR],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        # SpatiaLite so the geospatial app's PointField/PolygonField have
        # real geometry column types on top of sqlite
        'ENGINE': 'django.contrib.gis.db.backends.spatialite',
        'NAME': BASE_DIR / 'db.sqlite3',

    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'


CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
# Media files for model artifacts
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# AI explanation layer (ai_service)
#
# These settings configure the optional LLM layer that turns a machine
# learning prediction into a plain-language explanation. They are deliberately
# isolated from every ML setting above: the prediction engine reads none of
# them, so a missing key or an unreachable provider cannot affect scoring.
# ---------------------------------------------------------------------------


def _env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(name, default):
    try:
        return int(os.environ.get(name, '').strip() or default)
    except ValueError:
        return default


# Master switch. False disables the feature without removing credentials.
AI_EXPLANATIONS_ENABLED = _env_bool('AI_EXPLANATIONS_ENABLED', True)

# Key into the provider registry in ai_service/providers/__init__.py.
#
# Defaults to 'ollama': the free, open-source, fully local path. It needs
# no API key and no account, and the prediction context never leaves this
# machine -- also the strongest privacy position available for health
# data. 'anthropic' stays available for anyone wanting hosted quality and
# willing to pay per request.
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'ollama').strip() or 'ollama'

AI_MODEL = os.environ.get('AI_MODEL', 'llama3.2:3b').strip() or 'llama3.2:3b'
AI_MAX_TOKENS = _env_int('AI_MAX_TOKENS', 2000)
# Sized for local CPU inference, which is far slower than a hosted API.
# Measured on a 3B model without a GPU: ~80s ungrounded, ~160s with RAG
# passages injected, since the longer prompt costs real processing time.
# 300s leaves headroom for that plus variance; a hosted provider returns
# in seconds and is unaffected by the larger value.
AI_TIMEOUT_SECONDS = _env_int('AI_TIMEOUT_SECONDS', 300)

# Provider credentials. Read from the environment only - never hardcoded, and
# never returned by any API endpoint.
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '').strip()

# Endpoint for providers that talk to a host, currently Ollama. Blank means
# the provider's own default (http://localhost:11434). Local providers need
# no credentials at all -- each provider class declares whether it requires
# an API key, so leaving ANTHROPIC_API_KEY empty is correct when running
# AI_PROVIDER=ollama.
AI_BASE_URL = os.environ.get('AI_BASE_URL', '').strip()

# ---------------------------------------------------------------------------
# RAG knowledge base (ai_service.rag)
#
# Retrieval grounds AI explanations in trusted health guidance. It is
# strictly additive and strictly optional: with RAG_ENABLED False, or with
# sentence-transformers / chromadb absent, retrieval.get_retriever() returns
# NullRetriever and explanations are generated exactly as before.
#
# The dependency chain degrades one level at a time and never upward:
#   no knowledge base  -> ungrounded explanation
#   no LLM             -> no explanation, prediction unaffected
# ---------------------------------------------------------------------------

RAG_ENABLED = _env_bool('RAG_ENABLED', True)

# Where Chroma persists its index. Blank uses MEDIA_ROOT/chroma. Treated as a
# rebuildable cache: KnowledgeDocument/DocumentChunk are the system of record.
RAG_CHROMA_PATH = os.environ.get('RAG_CHROMA_PATH', '').strip()
RAG_COLLECTION_NAME = os.environ.get('RAG_COLLECTION_NAME', 'sti_knowledge').strip()

# Embedding model. 384 dimensions, 256-token input ceiling, ~90 MB.
RAG_EMBEDDING_MODEL = os.environ.get('RAG_EMBEDDING_MODEL', 'all-MiniLM-L6-v2').strip()

# Chunking, in CHARACTERS. See ai_service/rag/chunking.py for why characters
# rather than words: 500 words would exceed the encoder's 256-token limit and
# be silently truncated.
RAG_CHUNK_SIZE = _env_int('RAG_CHUNK_SIZE', 500)
RAG_CHUNK_OVERLAP = _env_int('RAG_CHUNK_OVERLAP', 100)

# How many passages to inject, and the cosine similarity below which a
# passage is treated as irrelevant. Returning nothing is safer than grounding
# an explanation in a weakly-related passage.
RAG_TOP_K = _env_int('RAG_TOP_K', 3)
RAG_MIN_SCORE = float(os.environ.get('RAG_MIN_SCORE', '0.35') or 0.35)
