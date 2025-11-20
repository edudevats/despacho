"""Blueprint de Dashboards"""
from flask import Blueprint
bp = Blueprint('dashboards', __name__)
from app.dashboards import routes
