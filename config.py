import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file in project root ONLY
# Get the directory where config.py is located (project root)
_config_dir = os.path.dirname(os.path.abspath(__file__))
_env_file = os.path.join(_config_dir, '.env')

# Load .env with explicit path to prevent searching parent directories
# dotenv_path parameter ensures it loads ONLY from the specified file
if os.path.exists(_env_file):
    load_dotenv(dotenv_path=_env_file, override=False)
# If .env doesn't exist, load_dotenv won't be called
# Environment variables can still come from system/server configuration

# Force timezone configuration globally
import time
os.environ['TZ'] = 'America/Mexico_City'
try:
    time.tzset()
except AttributeError:
    # time.tzset() is only available on Unix
    pass


# Sentinel value used to detect missing secrets at app-startup time.
# Validation runs in Config.validate() rather than at class-body load time so that
# importing config.py (e.g. for TestingConfig) does not require production env vars.
_MISSING_SECRET = None


class Config:
    """Base configuration"""
    # SECRET_KEY is mandatory in production. If the env var is missing, validate()
    # raises at app-startup time. No insecure hardcoded fallback exists.
    SECRET_KEY = os.environ.get('SECRET_KEY') or _MISSING_SECRET

    # Timezone - Mexico City
    TIMEZONE = 'America/Mexico_City'

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///sat_app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload folder - use absolute path based on config.py location
    # This ensures correct path even in WSGI context
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

    # Flask-WTF (CSRF Protection)
    WTF_CSRF_ENABLED = True
    # Tokens valid 1 hour. Reduces replay window vs the previous 7-day policy.
    WTF_CSRF_TIME_LIMIT = 3600
    
    # Flask-Caching
    CACHE_TYPE = os.environ.get('CACHE_TYPE') or 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutos
    CACHE_KEY_PREFIX = 'sat_app_'
    
    # Flask-Mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 'yes']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', '1', 'yes']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@satapp.local'
    MAIL_SUPPRESS_SEND = os.environ.get('MAIL_SUPPRESS_SEND', 'true').lower() in ['true', '1', 'yes']  # True for dev
    
    # Session
    # Reduced from 7 days to 1 day to limit stolen-cookie validity window.
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)

    # Security
    SESSION_COOKIE_SECURE = False  # Overridden to True in ProductionConfig
    SESSION_COOKIE_HTTPONLY = True
    # Stricter than Lax: prevents the cookie from being sent on top-level GETs
    # initiated by other origins, eliminating most CSRF vectors.
    SESSION_COOKIE_SAMESITE = 'Strict'

    # JWT for mobile API
    # Mandatory and must NOT collide with SECRET_KEY (separate trust domains).
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or _MISSING_SECRET
    JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS') or 72)
    # Issuer/audience claims for JWT validation (defense-in-depth against token confusion).
    JWT_ISSUER = os.environ.get('JWT_ISSUER') or 'sat-app'
    JWT_AUDIENCE = os.environ.get('JWT_AUDIENCE') or 'sat-mobile'

    @classmethod
    def validate(cls):
        """Validate that required secrets are present and well-formed.

        Called from create_app() after the config is selected. Subclasses
        (e.g. TestingConfig) override SECRET_KEY/JWT_SECRET_KEY to bypass
        this check with safe test values.
        """
        if not cls.SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY environment variable is required. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        if not cls.JWT_SECRET_KEY:
            raise RuntimeError(
                "JWT_SECRET_KEY environment variable is required. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        if cls.JWT_SECRET_KEY == cls.SECRET_KEY:
            raise RuntimeError(
                "JWT_SECRET_KEY must be different from SECRET_KEY (separate trust domains). "
                "Generate two distinct values."
            )
        if len(cls.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY is too short (minimum 32 characters).")
        if len(cls.JWT_SECRET_KEY) < 32:
            raise RuntimeError("JWT_SECRET_KEY is too short (minimum 32 characters).")
    
    # Barcode Lookup API (optional - for external product catalog)
    BARCODE_API_PROVIDER = os.environ.get('BARCODE_API_PROVIDER') or 'upcitemdb'  # upcitemdb, ean-search
    BARCODE_API_URL = os.environ.get('BARCODE_API_URL')
    BARCODE_API_KEY = os.environ.get('BARCODE_API_KEY')



class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    MAIL_SUPPRESS_SEND = True  # No enviar emails en desarrollo
    CACHE_TYPE = 'SimpleCache'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    MAIL_SUPPRESS_SEND = False
    SESSION_COOKIE_SECURE = True
    CACHE_TYPE = os.environ.get('CACHE_TYPE') or 'SimpleCache'
    # For Redis cache in production:
    # CACHE_TYPE = 'RedisCache'
    # CACHE_REDIS_URL = os.environ.get('REDIS_URL')


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing
    MAIL_SUPPRESS_SEND = True
    CACHE_TYPE = 'NullCache'
    # Provide safe deterministic test secrets so the validate() check passes.
    # These are NEVER used outside the test suite.
    SECRET_KEY = 'test-secret-key-for-pytest-only-do-not-use-in-prod-32chars'
    JWT_SECRET_KEY = 'test-jwt-secret-key-for-pytest-only-do-not-use-in-prod-32c'


# Config dictionary for easy access
# Default is ProductionConfig — fail-safe. Selecting an unsafe config requires
# explicit opt-in via FLASK_ENV=development or FLASK_ENV=testing.
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': ProductionConfig
}
