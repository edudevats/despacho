import os
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, limiter, cache, mail, csrf, migrate
from sqlalchemy import func, extract
from datetime import datetime, timedelta, timezone
from utils.timezone_helper import now_mexico, to_mexico_time
from utils.helpers import safe_redirect_target, find_company_invoice_xml_path, parse_invoice_xml_for_db, get_or_create_supplier, update_supplier_stats
from utils.decorators import admin_required, inventory_admin_required, require_company_perm
from models import *
from forms import *
from services.sat_service import SATService, SATError
from services.qr_service import QRService

logger = logging.getLogger(__name__)


auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
# Rate limit by IP: 5 attempts per minute and 30 per hour. Mitigates
# online brute-force / credential stuffing. Tune via RATELIMIT_STORAGE_URI
# to a Redis backend in multi-worker deployments.
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        # Compute hash check unconditionally to flatten timing side-channel
        # (M-2: user enumeration via login latency). The dummy hash is a
        # cached PBKDF2 of an unguessable string so the work factor matches
        # a real user lookup.
        from werkzeug.security import generate_password_hash as _ghash
        _DUMMY_HASH = getattr(login, '_dummy_hash', None)
        if _DUMMY_HASH is None:
            _DUMMY_HASH = _ghash('not-a-real-password-flat-timing')
            login._dummy_hash = _DUMMY_HASH
        if user:
            ok = check_password_hash(user.password_hash, password)
        else:
            # Burn equivalent CPU; result discarded.
            check_password_hash(_DUMMY_HASH, password)
            ok = False

        if user and ok:
            user.last_login = now_mexico()
            db.session.commit()
            login_user(user)
            return redirect(url_for('main.index'))
        else:
            flash('Usuario o contraseña incorrectos')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not check_password_hash(current_user.password_hash, current_password):
            flash('La contraseña actual es incorrecta.', 'error')
            return redirect(url_for('auth.change_password'))
        
        if new_password != confirm_password:
            flash('Las nuevas contraseñas no coinciden.', 'error')
            return redirect(url_for('auth.change_password'))
        
        # Update password
        current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        
        flash('Tu contraseña ha sido actualizada correctamente.', 'success')
        return redirect(url_for('main.index'))
        
    return render_template('change_password.html')

