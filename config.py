"""
Configuración del Sistema de Contaduría Multiclinicas
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuración base"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production-2024'

    # Base de datos SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'contaduria.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

    # Flask-Login
    REMEMBER_COOKIE_DURATION = timedelta(days=7)

    # Paginación
    ITEMS_PER_PAGE = 50

    # Reportes
    REPORTS_TEMP_FOLDER = os.path.join(basedir, 'temp_reports')

    # Timezone
    TIMEZONE = 'America/Mexico_City'

    # Formato de moneda
    CURRENCY_SYMBOL = '$'
    CURRENCY_FORMAT = '{:,.2f}'


class DevelopmentConfig(Config):
    """Configuración de desarrollo"""
    DEBUG = True
    SQLALCHEMY_ECHO = True  # Mostrar queries SQL en consola


class ProductionConfig(Config):
    """Configuración de producción"""
    DEBUG = False
    SQLALCHEMY_ECHO = False

    # En producción, estas deben venir de variables de entorno
    def __init__(self):
        if not os.environ.get('SECRET_KEY'):
            raise ValueError("No SECRET_KEY set for Flask application in production")


class TestingConfig(Config):
    """Configuración para testing"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Diccionario de configuraciones
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
