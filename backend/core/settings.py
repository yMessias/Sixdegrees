from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-secret-key-troque-em-producao')

debug_env = os.getenv('DEBUG')
if debug_env is None:
    # Por padrão, DEBUG=False em ambiente Render (RENDER é definido lá).
    DEBUG = os.getenv('RENDER') is None
else:
    DEBUG = debug_env.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

allowed_hosts_env = os.getenv('ALLOWED_HOSTS')
if allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_env.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

render_external_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if render_external_hostname and render_external_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_external_hostname)

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'api',
]

# DRF sem autenticação — API pública
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
}

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {}

cors_allowed_origins_env = os.getenv('CORS_ALLOWED_ORIGINS')
if cors_allowed_origins_env:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = [
        o.strip() for o in cors_allowed_origins_env.split(',') if o.strip()
    ]
else:
    CORS_ALLOW_ALL_ORIGINS = True

STATIC_URL = '/static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

TMDB_API_KEY = os.getenv('TMDB_API_KEY')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
SEARCH_DEEP_TIME_BUDGET_SECONDS = _env_int('SEARCH_DEEP_TIME_BUDGET_SECONDS', 180)
