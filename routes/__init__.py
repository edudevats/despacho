"""
Routes package - Flask Blueprints for modular route organization.
"""
from flask import Flask

def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask application."""
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.main import main_bp
    from routes.companies import companies_bp
    from routes.movements import movements_bp
    from routes.inventory import inventory_bp
    from routes.invoicing import invoicing_bp
    from routes.api import api_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(movements_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(invoicing_bp)
    app.register_blueprint(api_bp)
