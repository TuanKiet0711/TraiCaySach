# myproject/settings.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-(=*^!!)2o8co%_^o__is4x98d3!!k3a_j-00xj62^4^g+3um%e'
DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "localhost", ".ngrok-free.dev"]
CSRF_TRUSTED_ORIGINS = [
    "https://*.ngrok-free.dev",
]

INSTALLED_APPS = [
    'django.contrib.admin','django.contrib.auth','django.contrib.contenttypes',
    'django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles',
    'django.contrib.humanize','shop','rest_framework',
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

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / "templates"],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'django.template.context_processors.media',
        ],
    },
}]

WSGI_APPLICATION = 'myproject.wsgi.application'

DATABASES = {
    'default': {'ENGINE': 'django.db.backends.sqlite3','NAME': BASE_DIR / 'db.sqlite3'}
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ===== VNPay (điền đúng TMNCODE & HASHSECRET sandbox/production của bạn) =====
def _env(name, default=""):
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else v

VNPAY_TMNCODE     = "69EKU95U"   # Mã website (Terminal ID)
VNPAY_HASHSECRET  = "K4QASRVY6JC7MHH8IPXF2Q5PWBJVTNJD"  # Chuỗi bí mật

# ⚙️ URL thanh toán sandbox
VNPAY_PAYMENT_URL = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"

# ⚠️ PHẢI là HTTPS public URL và TRÙNG path trong urls.py bên dưới
PUBLIC_BASE = _env("PUBLIC_BASE", " https://ayesha-rankish-fatimah.ngrok-free.dev")
VNPAY_RETURN_URL    = f"{PUBLIC_BASE}/api/pay/vnpay/return/"
VNPAY_IPN_URL       = f"{PUBLIC_BASE}/api/pay/vnpay/ipn/"
