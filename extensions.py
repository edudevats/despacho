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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Database
db = SQLAlchemy()

# Authentication
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
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

# Rate limiting. Default storage is in-memory (NOT shared across workers);
# for multi-worker deployments configure RATELIMIT_STORAGE_URI to a Redis
# instance via env (e.g. redis://localhost:6379). The defaults below give
# coarse global protection; specific endpoints (login, etc.) must add their
# own @limiter.limit("...") decorator with stricter values.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per hour"],
    storage_uri="memory://",
)


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
    # Read storage URI from app config so production can point to Redis.
    storage_uri = app.config.get('RATELIMIT_STORAGE_URI') or 'memory://'
    limiter.init_app(app)
    # Override storage if explicitly configured (init_app already pulled defaults).
    if storage_uri != 'memory://':
        limiter._storage_uri = storage_uri

    return app
