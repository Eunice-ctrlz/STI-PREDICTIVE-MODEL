
from pathlib import Path
import os

# QGIS 4.0.2 GDAL paths
GDAL_LIBRARY_PATH = r"C:\Users\USER\Desktop\QGIS 4.0.2\bin\gdal309.dll"
GEOS_LIBRARY_PATH = r"C:\Users\USER\Desktop\QGIS 4.0.2\bin\geos_c.dll"

# Add QGIS bin to PATH for dependencies
os.environ['PATH'] = r"C:\Users\USER\Desktop\QGIS 4.0.2\bin;" + os.environ.get('PATH', '')
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


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

    'ninja',
    'rest_framework',
    'corsheaders',
    'preprocessing',
    'ml_pipeline',
    'geospatial',
    'patients',
    'prediction_engine',
    'moh_reporting',
    'data_ingestion',
    'compliance',
    'clinicians',
]


REPORTING = {
    'WHO_COUNTRY_CODE': 'KEN',
    'WHO_SUBMISSION_ENDPOINT': 'https://who.example.com/surveillance',  # Placeholder
    'AUTO_GENERATE_WEEKLY': True,
    'RETENTION_REPORTS_DAYS': 2555,  # 7 years
}
# Patient session settings
PATIENT_SESSION_TTL_HOURS = 24
PATIENT_MAX_ASSESSMENTS_PER_HOUR = 3
PATIENT_DATA_RETENTION_DAYS = 90  # Spec Section 5.2

# JWT settings for clinician auth
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

# Preprocessing defaults
PREPROCESSING_DEFAULTS = {
    'DP_EPSILON': 0.1,
    'K_ANONYMITY': 10,
    'MIN_GRID_SIZE_KM2': 25,
    'DATA_RETENTION_DAYS': 90,
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
CELERY_BEAT_SCHEDULE = {
    'generate-weekly-heatmaps': {
        'task': 'geospatial.tasks.generate_weekly_heatmaps',
        'schedule': 604800.0,  # 7 days in seconds
    },
     'quarterly-bias-audit': {
        'task': 'compliance.tasks.quarterly_bias_audit',
        'schedule': 7776000.0,  # 90 days
    },
    'daily-retention': {
        'task': 'compliance.tasks.daily_retention_enforcement',
        'schedule': 86400.0,  # 1 day
    },
    'annual-validation-review': {
        'task': 'compliance.tasks.annual_validation_review',
        'schedule': 31536000.0,  # 365 days
    },
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
