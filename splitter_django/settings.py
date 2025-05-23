"""
Django settings for splitter_django project - optimized for Fly.io + S3 + MVSEP.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Logging ---
logger = logging.getLogger("general_logger")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.propagate = False

# --- Security ---
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-default-dev-key-change-in-production")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [
    'localhost', '127.0.0.1', '.fly.dev',
    'www.songsplitter.net', 'songsplitter.net'
]

# --- App Definition ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'splitter.apps.SplitterConfig',
]

MIDDLEWARE = [
    'splitter.middleware.BlockBotMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'splitter.middleware.LicenseMiddleware',
]

ROOT_URLCONF = 'splitter_django.urls'

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

WSGI_APPLICATION = 'splitter_django.wsgi.application'

"""
# --- Database (SQLite + Fly Volume Mount) ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': '/data/db.sqlite3' if os.path.exists('/data') else os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}
"""

import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=os.getenv("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=True
    )
}

# --- Password Validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# --- Static / Media Files ---
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- Upload / Sessions ---
DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024  # 100MB
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- AWS / S3 Configuration (Optional) ---
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME", "us-west-2")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# --- MVSEP Configuration (Optional but needed for processing) ---
MVSEP_API_TOKEN = os.getenv('MVSEP_API_TOKEN')
MVSEP_TEMP_DIR = os.path.join(BASE_DIR, "media", "temp")
os.makedirs(MVSEP_TEMP_DIR, exist_ok=True)
MVSEP_MAX_FILE_SIZE = int(os.getenv('MVSEP_MAX_FILE_SIZE', str(100 * 1024 * 1024)))
MVSEP_TEMP_FILE_TTL = int(os.getenv('MVSEP_TEMP_FILE_TTL', str(86400)))

# --- Keygen Licensing (Optional) ---
# KEYGEN_ACCOUNT_ID = os.getenv("KEYGEN_ACCOUNT_ID")  # No longer needed

# --- GoHighLevel Configuration ---
GHL_API_KEY = os.getenv("GHL_API_KEY")
GHL_ACCESS_TAG = os.getenv("GHL_ACCESS_TAG", "splitter access")

# --- Security Settings in Production ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# --- CSRF Trusted Origins ---
CSRF_TRUSTED_ORIGINS = [
    'https://splitter-app.fly.dev',
    'https://mvsep-splitter.fly.dev',
    'https://songsplitter.net',
    'https://www.songsplitter.net'
]

# Initialize S3 client lazily
S3 = None

def get_s3_client():
    """Initialize S3 client if AWS credentials are available"""
    global S3
    if S3 is None and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        try:
            import boto3
            S3 = boto3.client(
                's3',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION_NAME
            )
            logger.info("Successfully initialized S3 client")
        except Exception as e:
            logger.error(f"Error initializing S3 client: {str(e)}")
            return None
    return S3