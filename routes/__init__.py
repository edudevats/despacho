"""
Routes package - Flask Blueprints for modular route organization.

This package contains all the route blueprints for the application:
- auth: Authentication routes (login, logout, password change)
- companies: Company management routes
- taxes: Tax calculation and payment routes
- api: API endpoints

Usage:
    from routes import register_blueprints
    register_blueprints(app)
"""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask application."""
    from routes.auth import auth_bp
    from routes.companies import companies_bp
    from routes.taxes import taxes_bp
    from routes.api import api_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(taxes_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
