"""
Rutas principales
"""
from flask import render_template, redirect, url_for
from flask_login import login_required, current_user
from app.main import bp


@bp.route('/')
@bp.route('/index')
@login_required
def index():
    """
    Página principal - redirige al dashboard correspondiente según el rol
    """
    if current_user.es_admin_despacho():
        return redirect(url_for('dashboards.despacho'))
    elif current_user.es_principal_organizacion():
        return redirect(url_for('dashboards.organizacion'))
    elif current_user.es_principal_sucursal() or current_user.es_secundario_pos():
        return redirect(url_for('dashboards.sucursal'))
    else:
        return redirect(url_for('auth.login'))
