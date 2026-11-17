"""
Django settings for the ESIEM project.

Configuration that changes between environments is read from environment
variables (see README.md).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path):
    """Load KEY=VALUE lines from a local .env file; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(BASE_DIR / '.env')


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes', 'on')


SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-vtzw9yta@)+4g58r)jmk=5ypwu#3h7qdp)g^nq$r1+3n^^j0)p',
)
DEBUG = env_bool('DJANGO_DEBUG', True)
ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if o]


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'accounts',
    'core',
    'crm',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'esiem.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.event',
            ],
        },
    },
]

WSGI_APPLICATION = 'esiem.wsgi.application'


# PostgreSQL is the only supported database.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('ESIEM_DB_NAME', 'esiem'),
        'USER': os.environ.get('ESIEM_DB_USER', 'esiem'),
        'PASSWORD': os.environ.get('ESIEM_DB_PASSWORD', ''),
        'HOST': os.environ.get('ESIEM_DB_HOST', 'localhost'),
        'PORT': os.environ.get('ESIEM_DB_PORT', '5432'),
        'CONN_MAX_AGE': 60,
        'CONN_HEALTH_CHECKS': True,
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'crm:panel'
LOGOUT_REDIRECT_URL = 'core:home'


LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'Europe/Madrid'
USE_I18N = True
USE_TZ = True


STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Upload limit for dossiers, logos and banners (bytes).
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# .txt email templates loaded by the CRM email module.
EMAIL_TEMPLATES_DIR = BASE_DIR / 'email_templates'


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}


# Email: SMTP when ESIEM_SMTP_HOST is set, console output otherwise.
DEFAULT_FROM_EMAIL = os.environ.get('ESIEM_FROM_EMAIL', 'ESIEM <no-reply@esiem.es>')
# False hides "Enviar automáticamente" in the CRM: organizers send from their own Outlook and register it.
EMAIL_AUTOMATIC_SENDING = env_bool('ESIEM_EMAIL_AUTOMATIC', True)

if os.environ.get('ESIEM_SMTP_HOST'):
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'OPTIONS': {
                'host': os.environ['ESIEM_SMTP_HOST'],
                'port': int(os.environ.get('ESIEM_SMTP_PORT', 587)),
                'username': os.environ.get('ESIEM_SMTP_USER', ''),
                'password': os.environ.get('ESIEM_SMTP_PASSWORD', ''),
                'use_tls': env_bool('ESIEM_SMTP_TLS', True),
            },
        },
    }
else:
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.console.EmailBackend',
        },
    }


if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
