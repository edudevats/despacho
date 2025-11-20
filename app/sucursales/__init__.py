"""Blueprint de Sucursales"""
from flask import Blueprint

bp = Blueprint('sucursales', __name__)

from app.sucursales import routes
