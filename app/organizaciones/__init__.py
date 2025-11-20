"""Blueprint de Organizaciones"""
from flask import Blueprint

bp = Blueprint('organizaciones', __name__)

from app.organizaciones import routes
