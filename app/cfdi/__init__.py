"""
Blueprint de CFDI
Gestión de facturas digitales XML/CFDI
"""
from flask import Blueprint

bp = Blueprint('cfdi', __name__)

from app.cfdi import routes
