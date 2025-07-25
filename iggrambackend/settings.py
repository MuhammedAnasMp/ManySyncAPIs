import os
from pathlib import Path
import environ
from firebase_admin import credentials
import firebase_admin

# Initialize environment variables
env = environ.Env()
environ.Env.read_env()

BASE_DIR = Path(__file__).resolve().parent.parent

# Firebase Configuration
cred = credentials.Certificate({
    "type": os.environ.get('FIREBASE_TYPE'),
    "project_id": os.environ.get('FIREBASE_PROJECT_ID'),
    "private_key_id": os.environ.get('FIREBASE_PRIVATE_KEY_ID'),
    "private_key": os.environ.get('FIREBASE_PRIVATE_KEY').replace("\\n", "\n"),
    "client_email": os.environ.get('FIREBASE_CLIENT_EMAIL'),
    "client_id": os.environ.get('FIREBASE_CLIENT_ID'),
    "auth_uri": os.environ.get('FIREBASE_AUTH_URI'),
    "token_uri": os.environ.get('FIREBASE_TOKEN_URI'),
    "auth_provider_x509_cert_url": os.environ.get('FIREBASE_AUTH_PROVIDER_X509_CERT_URL'),
    "client_x509_cert_url": os.environ.get('FIREBASE_CLIENT_X509_CERT_URL')
})

firebase_admin.initialize_app(cred)

# Secret key and debugging settings
SECRET_KEY = 'django-insecure-qrx0xn=$q-odldswv!7sr&c*7cl)zkmefx!7yi69w5t(+rxl^v'

DEBUG = os.environ.get("DEBUG")
DEVELOPMENTDEBUG = os.environ.get("DEVELOPMENTDEBUG")

# CORS and allowed hosts settings
if DEBUG == "True":
    print('DEVELOPMENT')
    ALLOWED_HOSTS = ['*']
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.43.106:5173"
    ]
    CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "https://yourdomain.com",  # if applicable
]

else:
    if DEVELOPMENTDEBUG == "True":
        print('PRODUCTION LOCAL')
        ALLOWED_HOSTS = ['localhost', '127.0.0.1', os.getenv('BACKEND_HOST', '')]
        CORS_ALLOWED_ORIGINS = ['http://localhost:5173',
                                'http://localhost:4173', os.getenv('FRONTEND_DOMAIN', '')]
        CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "https://yourdomain.com",  # if applicable
]

    else:
        print("PRODUCTION")
        ALLOWED_HOSTS = [os.getenv('BACKEND_HOST', '')]
        CORS_ALLOWED_ORIGINS = [os.getenv('FRONTEND_DOMAIN', '')]
        CSRF_TRUSTED_ORIGINS = [os.getenv('FRONTEND_DOMAIN', '')]


CORS_ALLOW_CREDENTIALS = True

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.authentication',
    'apps.instagram_accounts',
    'rest_framework',
    'corsheaders',
    'cloudinary',
    'cloudinary_storage',
    'django_celery_beat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# REST Framework Authentication and 
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
      'apps.authentication.authentication.FirebaseAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
# Database Configuration
if DEBUG == "True":
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get("MYSQL_DB_NAME"),
            'USER': os.environ.get("MYSQL_USER"),
            'PASSWORD': os.environ.get("MYSQL_PASSWORD"),
            'HOST': os.environ.get("MYSQL_HOST"),
            'PORT': os.environ.get("MYSQL_PORT"),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Static files and media storage
STATIC_URL = '/static/'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Default auto field for primary keys
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# WSGI and root URL configuration
WSGI_APPLICATION = 'iggrambackend.wsgi.application'
ROOT_URLCONF = 'iggrambackend.urls'

# Templates Configuration
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

# Firebase Authentication Model
AUTH_USER_MODEL = 'authentication.UserProfile'

# Cloudinary Configuration
CLOUDINARY = {
    'cloud_name': os.environ.get('CLOUDINARY_CLOUD_NAME'),
    'api_key': os.environ.get('CLOUDINARY_API_KEY'),
    'api_secret': os.environ.get('CLOUDINARY_API_SECRET'),
}