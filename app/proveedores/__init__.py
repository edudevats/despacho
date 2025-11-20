"""
Blueprint de Proveedores
"""
from flask import Blueprint

bp = Blueprint('proveedores', __name__, url_prefix='/proveedores')

from app.proveedores import routes
