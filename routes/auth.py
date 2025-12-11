"""
Authentication routes - Login, Logout, Password management.
"""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models import User
from cli import validate_password_strength

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login page and handler."""
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Por favor ingresa usuario y contraseña.', 'warning')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            logger.info(f"User '{username}' logged in successfully")
            
            # Redirect to next page if specified
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            logger.warning(f"Failed login attempt for username: {username}")
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out the current user."""
    username = current_user.username
    logout_user()
    logger.info(f"User '{username}' logged out")
    flash('Has cerrado sesión correctamente.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change current user's password."""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validate current password
        if not check_password_hash(current_user.password_hash, current_password):
            flash('La contraseña actual es incorrecta.', 'error')
            return redirect(url_for('auth.change_password'))
        
        # Check passwords match
        if new_password != confirm_password:
            flash('Las nuevas contraseñas no coinciden.', 'error')
            return redirect(url_for('auth.change_password'))
        
        # Validate password strength
        is_valid, message = validate_password_strength(new_password)
        if not is_valid:
            flash(f'Contraseña débil: {message}', 'error')
            return redirect(url_for('auth.change_password'))
        
        # Update password
        current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        
        logger.info(f"User '{current_user.username}' changed password")
        flash('Tu contraseña ha sido actualizada correctamente.', 'success')
        return redirect(url_for('index'))
    
    return render_template('change_password.html')
