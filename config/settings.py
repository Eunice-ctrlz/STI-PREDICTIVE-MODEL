
from pathlib import Path

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / 'frontend'

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

