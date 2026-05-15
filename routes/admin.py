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


admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/users')
@admin_required
def admin_users():
    """List all users"""
    users = User.query.order_by(User.username).all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/admin/users/add', methods=['GET', 'POST'])
@admin_required
def admin_add_user():
    """Create new user"""
    form = UserForm()
    companies = Company.query.order_by(Company.name).all()

    if form.validate_on_submit():
        # Check if username exists
        if User.query.filter_by(username=form.username.data).first():
            flash('El nombre de usuario ya existe.', 'error')
            return render_template('admin/user_form.html', form=form, companies=companies, action='crear')

        # Check if email exists (if provided)
        if form.email.data and User.query.filter_by(email=form.email.data).first():
            flash('El email ya está registrado.', 'error')
            return render_template('admin/user_form.html', form=form, companies=companies, action='crear')

        # Create user
        user = User(
            username=form.username.data,
            email=form.email.data or None,
            password_hash=generate_password_hash(form.password.data) if form.password.data else generate_password_hash('changeme'),
            is_active=form.is_active.data,
            is_admin=form.is_admin.data
        )
        db.session.add(user)
        db.session.flush()  # Get user.id

        # Process company access
        for company in companies:
            if request.form.get(f'company_{company.id}'):
                access = UserCompanyAccess(
                    user_id=user.id,
                    company_id=company.id,
                    perm_dashboard=request.form.get(f'perm_dashboard_{company.id}') == 'on',
                    perm_sync=request.form.get(f'perm_sync_{company.id}') == 'on',
                    perm_inventory=request.form.get(f'perm_inventory_{company.id}') == 'on',
                    perm_invoices=request.form.get(f'perm_invoices_{company.id}') == 'on',
                    perm_ppd=request.form.get(f'perm_ppd_{company.id}') == 'on',
                    perm_taxes=request.form.get(f'perm_taxes_{company.id}') == 'on',
                    perm_sales=request.form.get(f'perm_sales_{company.id}') == 'on',
                    perm_facturacion=request.form.get(f'perm_facturacion_{company.id}') == 'on',
                    perm_inventory_admin=request.form.get(f'perm_inventory_admin_{company.id}') == 'on'
                )
                db.session.add(access)

        db.session.commit()
        flash(f'Usuario "{user.username}" creado correctamente.', 'success')
        return redirect(url_for('admin.admin_users'))

    # Set defaults for new user
    form.is_active.data = True
    return render_template('admin/user_form.html', form=form, companies=companies, action='crear')

@admin_bp.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_user(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    companies = Company.query.order_by(Company.name).all()

    # Get current access for this user
    user_access = {access.company_id: access for access in user.company_access}

    if form.validate_on_submit():
        # Check if username exists (excluding current user)
        existing = User.query.filter_by(username=form.username.data).first()
        if existing and existing.id != user_id:
            flash('El nombre de usuario ya existe.', 'error')
            return render_template('admin/user_form.html', form=form, user=user, companies=companies, user_access=user_access, action='editar')

        # Check if email exists (if provided, excluding current user)
        if form.email.data:
            existing = User.query.filter_by(email=form.email.data).first()
            if existing and existing.id != user_id:
                flash('El email ya está registrado.', 'error')
                return render_template('admin/user_form.html', form=form, user=user, companies=companies, user_access=user_access, action='editar')

        # Update user
        user.username = form.username.data
        user.email = form.email.data or None
        if form.password.data:
            user.password_hash = generate_password_hash(form.password.data)
        user.is_active = form.is_active.data
        user.is_admin = form.is_admin.data

        # Clear existing access
        UserCompanyAccess.query.filter_by(user_id=user_id).delete()

        # Process company access
        for company in companies:
            if request.form.get(f'company_{company.id}'):
                access = UserCompanyAccess(
                    user_id=user.id,
                    company_id=company.id,
                    perm_dashboard=request.form.get(f'perm_dashboard_{company.id}') == 'on',
                    perm_sync=request.form.get(f'perm_sync_{company.id}') == 'on',
                    perm_inventory=request.form.get(f'perm_inventory_{company.id}') == 'on',
                    perm_invoices=request.form.get(f'perm_invoices_{company.id}') == 'on',
                    perm_ppd=request.form.get(f'perm_ppd_{company.id}') == 'on',
                    perm_taxes=request.form.get(f'perm_taxes_{company.id}') == 'on',
                    perm_sales=request.form.get(f'perm_sales_{company.id}') == 'on',
                    perm_facturacion=request.form.get(f'perm_facturacion_{company.id}') == 'on',
                    perm_inventory_admin=request.form.get(f'perm_inventory_admin_{company.id}') == 'on'
                )
                db.session.add(access)

        db.session.commit()
        flash(f'Usuario "{user.username}" actualizado correctamente.', 'success')
        return redirect(url_for('admin.admin_users'))

    return render_template('admin/user_form.html', form=form, user=user, companies=companies, user_access=user_access, action='editar')

@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    """Delete user"""
    user = User.query.get_or_404(user_id)

    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('No puedes eliminar tu propio usuario.', 'error')
        return redirect(url_for('admin.admin_users'))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'Usuario "{username}" eliminado.', 'success')
    return redirect(url_for('admin.admin_users'))

