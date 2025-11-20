"""Blueprint de Categorías"""
from flask import Blueprint
bp = Blueprint('categorias', __name__)
from app.categorias import routes
