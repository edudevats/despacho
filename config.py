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


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
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
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hora
    
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
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Security
    SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # JWT for mobile API
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS') or 72)
    
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


# Config dictionary for easy access
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
