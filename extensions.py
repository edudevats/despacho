"""
Flask Extensions
Centralizes all Flask extension instances for the application.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect

# Database
db = SQLAlchemy()

# Authentication
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'

# Database migrations
migrate = Migrate()

# Email
mail = Mail()

# Caching
cache = Cache()

# CSRF Protection
csrf = CSRFProtect()


def init_extensions(app):
    """
    Initialize all Flask extensions with the application instance.
    
    Args:
        app: Flask application instance
    """
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    cache.init_app(app)
    csrf.init_app(app)
    
    return app
