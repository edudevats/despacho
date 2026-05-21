from flask import Flask, flash, redirect, request, url_for
import os
import logging

# Load environment variables FIRST (before importing config)
from dotenv import load_dotenv
load_dotenv()

from config import Config
from extensions import db, login_manager, init_extensions
from models import User
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from utils.helpers import safe_redirect_target, format_currency, chunk_split

logger = logging.getLogger(__name__)

# Define project root directory (absolute path to the directory containing app.py)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def create_app(config_class=Config):
    # Fail-fast if SECRET_KEY / JWT_SECRET_KEY are missing or weak.
    config_class.validate()

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize all extensions
    init_extensions(app)
    
    # Setup logging
    from logging_config import setup_logging
    setup_logging(app)
    
    # Custom Jinja2 filter for currency formatting with thousands separators
    app.template_filter('format_currency')(format_currency)
    app.template_filter('chunk_split')(chunk_split)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        flash('La página expiró por inactividad. Hemos recargado la página para que puedas continuar de forma segura.', 'warning')
        
        # Devolver una vista más estética con recarga automática por Javascript,
        # evitando la pantalla blanca o el 405 Method Not Allowed en redirecciones POST.
        html_content = """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Recargando sesión...</title>
            <style>
                body {
                    font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background-color: #f8f9fa;
                    color: #495057;
                    text-align: center;
                }
                .loader {
                    border: 4px solid #f3f3f3;
                    border-top: 4px solid #198754;
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 1rem auto;
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
            <script>
                // Recargar a la página anterior de forma segura o al inicio
                setTimeout(function() {
                    var target = document.referrer ? document.referrer : '/';
                    window.location.replace(target);
                }, 800);
            </script>
        </head>
        <body>
            <div>
                <div class="loader"></div>
                <h2>Sesión protegida</h2>
                <p>Recargando la página de forma segura...</p>
            </div>
        </body>
        </html>
        """
        return html_content, 200

    @app.context_processor
    def inject_inventory_admin_helper():
        def is_inv_admin(company_id):
            if not current_user.is_authenticated:
                return False
            return current_user.is_inventory_admin_for(company_id)

        def has_any_perm(*perm_names):
            if not current_user.is_authenticated:
                return False
            return current_user.has_any_perm(*perm_names)

        def has_company_perm(company_id, *perm_names):
            if not current_user.is_authenticated:
                return False
            return current_user.has_company_perm(company_id, *perm_names)

        return {
            'is_inv_admin': is_inv_admin,
            'has_any_perm': has_any_perm,
            'has_company_perm': has_company_perm,
        }

    # Register all blueprints
    from routes import register_blueprints
    register_blueprints(app)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
