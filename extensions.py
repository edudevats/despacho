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

# ── Rate Limiter (desactivado temporalmente) ─────────────────────────────────
# Flask-Limiter no está instalado en este entorno. Se usa un stub no-op para
# que la app arranque sin errores. Cuando instales Flask-Limiter en el server,
# basta con descomentar las líneas de abajo y eliminar el stub.
#
# from flask_limiter import Limiter
# from flask_limiter.util import get_remote_address

class _NoOpLimiter:
    """Stub that replaces Flask-Limiter when the package is not installed.
    All decorators become no-ops; the app runs without rate limiting.
    """
    def init_app(self, app):
        pass

    def limit(self, *args, **kwargs):
        """Return a no-op decorator."""
        def decorator(f):
            return f
        return decorator

    def exempt(self, f):
        return f

limiter = _NoOpLimiter()


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
    limiter.init_app(app)

    return app
