"""
Factory Pattern para el Sistema de Contaduria
Inicializa la aplicacion Flask y todas sus extensiones
"""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import config
import os

# Instancias de extensiones
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config_name='default'):
    """
    Factory para crear la aplicacion Flask

    Args:
        config_name: Nombre de la configuracion ('development', 'production', 'testing')

    Returns:
        app: Instancia configurada de Flask
    """
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Inicializar extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Configurar Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor inicia sesion para acceder a esta pagina.'
    login_manager.login_message_category = 'warning'

    # Importar modelos para que Flask-Migrate los reconozca
    from app import models

    # Registrar blueprints
    register_blueprints(app)

    # Configurar manejadores de errores
    register_error_handlers(app)

    # Configurar contexto de plantillas
    register_template_context(app)

    # Crear directorios necesarios
    create_directories(app)

    return app


def register_blueprints(app):
    """Registra todos los blueprints de la aplicacion"""

    # Blueprint de autenticacion
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Blueprint principal
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    # ==================== BLUEPRINTS ACTUALIZADOS PARA 4 NIVELES ====================

    # Blueprint de organizaciones (NUEVO)
    from app.organizaciones import bp as organizaciones_bp
    app.register_blueprint(organizaciones_bp, url_prefix='/organizaciones')

    # Blueprint de sucursales (renombrado de clinicas)
    from app.sucursales import bp as sucursales_bp
    app.register_blueprint(sucursales_bp, url_prefix='/sucursales')

    # Blueprint de categorias (ACTUALIZADO - soporta org + sucursal)
    from app.categorias import bp as categorias_bp
    app.register_blueprint(categorias_bp, url_prefix='/categorias')

    # ==================== BLUEPRINTS EN PROCESO DE ACTUALIZACIÓN ====================

    # Blueprint de usuarios (ACTUALIZADO - soporta jerarquía de 4 niveles)
    from app.usuarios import bp as usuarios_bp
    app.register_blueprint(usuarios_bp, url_prefix='/usuarios')

    # Blueprint de movimientos (ACTUALIZADO - soporta jerarquía + categorías híbridas)
    from app.movimientos import bp as movimientos_bp
    app.register_blueprint(movimientos_bp, url_prefix='/movimientos')

    # Blueprint de dashboards (ACTUALIZADO - 3 dashboards jerárquicos)
    from app.dashboards import bp as dashboards_bp
    app.register_blueprint(dashboards_bp, url_prefix='/dashboard')

    # Blueprint de reportes (ACTUALIZADO - reportes por sucursal y consolidados)
    from app.reportes import bp as reportes_bp
    app.register_blueprint(reportes_bp, url_prefix='/reportes')

    # Blueprint de CFDI (ACTUALIZADO - gestión por sucursal)
    from app.cfdi import bp as cfdi_bp
    app.register_blueprint(cfdi_bp, url_prefix='/cfdi')

    # Blueprint de proveedores (ACTUALIZADO - gestión por sucursal)
    from app.proveedores import bp as proveedores_bp
    app.register_blueprint(proveedores_bp, url_prefix='/proveedores')


def register_error_handlers(app):
    """Registra manejadores de errores personalizados"""

    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        from flask import render_template
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        db.session.rollback()
        return render_template('errors/500.html'), 500


def register_template_context(app):
    """Registra variables y funciones disponibles en todas las plantillas"""

    @app.context_processor
    def utility_processor():
        from datetime import datetime

        def format_currency(amount):
            """Formatea un numero como moneda"""
            if amount is None:
                amount = 0
            return f"${amount:,.2f}"

        def format_date(date):
            """Formatea una fecha"""
            if date is None:
                return ''
            return date.strftime('%d/%m/%Y')

        def format_datetime(dt):
            """Formatea una fecha y hora"""
            if dt is None:
                return ''
            return dt.strftime('%d/%m/%Y %H:%M')

        return dict(
            format_currency=format_currency,
            format_date=format_date,
            format_datetime=format_datetime,
            now=datetime.utcnow()
        )


def create_directories(app):
    """Crea directorios necesarios si no existen"""
    directories = [
        app.config['UPLOAD_FOLDER'],
        os.path.join(app.config['UPLOAD_FOLDER'], 'comprobantes'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'cfdi'),
        app.config['REPORTS_TEMP_FOLDER']
    ]

    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    """
    Callback requerido por Flask-Login para cargar un usuario
    """
    from app.models import Usuario
    return Usuario.query.get(int(user_id))
