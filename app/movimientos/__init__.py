"""Blueprint de Movimientos"""
from flask import Blueprint
bp = Blueprint('movimientos', __name__)
from app.movimientos import routes
