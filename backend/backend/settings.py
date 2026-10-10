"""
Django settings for backend project.

Django 5.2 LTS settings with explicit development/private profiles.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.2/ref/settings/
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

from backend.runtime_config import load_runtime

# Development remains compatible; private configuration must be explicitly valid.
globals().update(load_runtime(BASE_DIR, 'django-insecure-o9i2bh5!+++d(4wqi%h7q(h+f)h(_2%#r%f+z&+c2cwc=i%e$y'))


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'corsheaders',
    # Local apps
    'declaration',
    'deployment',
    'encoding',
    'evaluation',
    'feature_card',
    'modeling',
    'preprocessing',
    'ai_assistant',
    'access_control',
    'execution_jobs',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'access_control.session_middleware.SessionAuthorityMiddleware',
    'access_control.project_http.ProjectResponseMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

AUTHENTICATION_BACKENDS = ['access_control.auth_backend.GovernedModelBackend']


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Media files
MEDIA_URL = '/media/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Session credentials are accepted only from explicitly configured origins.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated', 'access_control.storage.ManagedRequestReferences', 'access_control.project_http.ProjectAccessPermission'],
}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8 * 60 * 60

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Allow larger request bodies for pipeline checkpoint state (modeling status can be large)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB (default is 2.5 MB)


# OpenAI API key for AI Assistant (set via environment variable)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# Knowledge-bank vector RAG (OpenAI embeddings + local Chroma)
OPENAI_EMBEDDING_MODEL = os.environ.get(
    'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'
)
CHROMA_PERSIST_DIR = os.environ.get(
    'CHROMA_PERSIST_DIR',
    str(BASE_DIR / '.chroma' / 'knowledge-bank'),
)
# hybrid | vector | lexical — hybrid merges Chroma cosine with lexical ranks
RAG_MODE = os.environ.get('RAG_MODE', 'hybrid').strip().lower() or 'hybrid'
# Optional override for Prometa retrieval.namespace (corpus/collection id).
# Empty → use the Chroma collection name (declarai-knowledge-bank).
RETRIEVAL_NAMESPACE = os.environ.get('RETRIEVAL_NAMESPACE', '').strip()
# Redis TTL for per-text embedding vectors (default 7 days)
try:
    EMBEDDING_CACHE_TTL = int(
        os.environ.get('EMBEDDING_CACHE_TTL', str(60 * 60 * 24 * 7))
    )
except (TypeError, ValueError):
    EMBEDDING_CACHE_TTL = 60 * 60 * 24 * 7

from execution_jobs.config import load_job_config
globals().update(load_job_config(globals()['DECLARAI_RUNTIME_PROFILE']))
