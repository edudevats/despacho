"""Blueprint de Usuarios"""
from flask import Blueprint
bp = Blueprint('usuarios', __name__)
from app.usuarios import routes
