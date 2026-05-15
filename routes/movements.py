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


movements_bp = Blueprint('movements', __name__)

@movements_bp.route('/companies/<int:company_id>/movements')
@login_required
def company_movements(company_id):
    """Redirect to unified search page for specific company"""
    return redirect(url_for('companies.search_invoices', company_id=company_id))

@movements_bp.route('/categories')
@login_required
def categories_list():
    """Show list of companies to manage categories"""
    companies_list = current_user.accessible_companies_with_perm('inventory', 'inventory_admin')
    return render_template('categories_list.html', companies=companies_list)

@movements_bp.route('/suppliers')
@login_required
def suppliers_list():
    """Show list of companies to manage suppliers"""
    companies_list = current_user.accessible_companies_with_perm('inventory', 'inventory_admin')
    return render_template('suppliers_list.html', companies=companies_list)

@movements_bp.route('/companies/<int:company_id>/categories/create', methods=['GET', 'POST'])
@login_required
@require_company_perm('inventory_admin')
def create_category(company_id):
    """Crear nueva categoría"""
    company = Company.query.get_or_404(company_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        cat_type = request.form.get('type')
        description = request.form.get('description')
        color = request.form.get('color', '#6c757d')
        
        category = Category(
            company_id=company_id,
            name=name,
            type=cat_type,
            description=description,
            color=color,
            is_default=False
        )
        
        db.session.add(category)
        db.session.commit()
        
        flash(f'Categoría "{name}" creada exitosamente', 'success')
        return redirect(url_for('inventory.categories', company_id=company_id))
    
    return render_template('categories/create.html', company=company)

@movements_bp.route('/companies/<int:company_id>/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
@require_company_perm('inventory_admin')
def edit_category(company_id, category_id):
    """Editar categoría existente"""
    company = Company.query.get_or_404(company_id)
    category = Category.query.get_or_404(category_id)
    
    if category.company_id != company_id:
        flash('Categoría no encontrada', 'error')
        return redirect(url_for('inventory.categories', company_id=company_id))
    
    if request.method == 'POST':
        category.name = request.form.get('name')
        category.description = request.form.get('description')
        category.color = request.form.get('color')
        
        db.session.commit()
        flash(f'Categoría "{category.name}" actualizada', 'success')
        return redirect(url_for('inventory.categories', company_id=company_id))

@movements_bp.route('/companies/<int:company_id>/taxes')
@login_required
@require_company_perm('taxes')
def taxes_dashboard(company_id):
    """Dashboard de Impuestos con IVA, ISR y resumen anual"""
    company = Company.query.get_or_404(company_id)
    
    today = now_mexico()
    current_year = today.year
    
    # Calculate monthly tax data
    monthly_tax_data = []
    month_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    # Annual totals
    annual_iva_to_pay = 0
    annual_iva_paid = 0
    annual_isr_estimated = 0
    annual_isr_paid = 0
    annual_income = 0
    annual_expense = 0
    
    # Chart data arrays
    chart_months = []
    chart_iva_collected = []
    chart_iva_deductible = []
    chart_isr_estimated = []
    
    for month_num in range(1, 13):
        # IVA Trasladado (Cobrado en Ventas) - invoices where company is the issuer
        iva_collected = db.session.query(func.sum(Invoice.tax)).filter(
            Invoice.company_id == company_id,
            Invoice.issuer_rfc == company.rfc,  # Company issued this invoice (income)
            extract('month', Invoice.date) == month_num,
            extract('year', Invoice.date) == current_year
        ).scalar() or 0
        
        # IVA Acreditable (Pagado en Gastos) - invoices where company is the receiver
        iva_deductible = db.session.query(func.sum(Invoice.tax)).filter(
            Invoice.company_id == company_id,
            Invoice.receiver_rfc == company.rfc,  # Company received this invoice (expense)
            extract('month', Invoice.date) == month_num,
            extract('year', Invoice.date) == current_year
        ).scalar() or 0
        
        # Ingresos del mes (para ISR) - invoices where company is the issuer
        month_income = db.session.query(func.sum(Invoice.subtotal)).filter(
            Invoice.company_id == company_id,
            Invoice.issuer_rfc == company.rfc,  # Company issued this invoice (income)
            extract('month', Invoice.date) == month_num,
            extract('year', Invoice.date) == current_year
        ).scalar() or 0
        
        # Egresos del mes (para ISR) - invoices where company is the receiver
        month_expense = db.session.query(func.sum(Invoice.subtotal)).filter(
            Invoice.company_id == company_id,
            Invoice.receiver_rfc == company.rfc,  # Company received this invoice (expense)
            extract('month', Invoice.date) == month_num,
            extract('year', Invoice.date) == current_year
        ).scalar() or 0
        
        # Net IVA Position (+ a pagar, - a favor)
        net_iva = iva_collected - iva_deductible
        
        # ISR Estimado (30% de utilidad bruta, solo si es positiva)
        profit = month_income - month_expense
        isr_estimated = max(0, profit * 0.30)
        
        # IVA Payments made
        iva_payments = TaxPayment.query.filter_by(
            company_id=company_id,
            period_month=month_num,
            period_year=current_year,
            tax_type='IVA'
        ).all()
        iva_paid_amount = sum(p.amount for p in iva_payments)
        
        # ISR Payments made
        isr_payments = TaxPayment.query.filter_by(
            company_id=company_id,
            period_month=month_num,
            period_year=current_year,
            tax_type='ISR'
        ).all()
        isr_paid_amount = sum(p.amount for p in isr_payments)
        
        # Accumulate annual totals
        if net_iva > 0:
            annual_iva_to_pay += net_iva
        annual_iva_paid += iva_paid_amount
        annual_isr_estimated += isr_estimated
        annual_isr_paid += isr_paid_amount
        annual_income += month_income
        annual_expense += month_expense
        
        # Chart data
        chart_months.append(month_names[month_num - 1][:3])  # Abbreviated
        chart_iva_collected.append(float(iva_collected))
        chart_iva_deductible.append(float(iva_deductible))
        chart_isr_estimated.append(float(isr_estimated))
        
        monthly_tax_data.append({
            'month_num': month_num,
            'month_name': month_names[month_num - 1],
            'iva_collected': float(iva_collected),
            'iva_deductible': float(iva_deductible),
            'net_iva': float(net_iva),
            'iva_paid_amount': float(iva_paid_amount),
            'iva_difference': float(net_iva - iva_paid_amount),
            'income': float(month_income),
            'expense': float(month_expense),
            'profit': float(profit),
            'isr_estimated': float(isr_estimated),
            'isr_paid_amount': float(isr_paid_amount),
            'isr_difference': float(isr_estimated - isr_paid_amount)
        })
    
    # Annual summary
    annual_summary = {
        'iva_to_pay': float(annual_iva_to_pay),
        'iva_paid': float(annual_iva_paid),
        'iva_pending': float(annual_iva_to_pay - annual_iva_paid),
        'isr_estimated': float(annual_isr_estimated),
        'isr_paid': float(annual_isr_paid),
        'isr_pending': float(annual_isr_estimated - annual_isr_paid),
        'total_income': float(annual_income),
        'total_expense': float(annual_expense),
        'total_profit': float(annual_income - annual_expense)
    }
    
    # Chart data for JavaScript
    chart_data = {
        'months': chart_months,
        'iva_collected': chart_iva_collected,
        'iva_deductible': chart_iva_deductible,
        'isr_estimated': chart_isr_estimated
    }
        
    return render_template('taxes/dashboard.html', 
                         company=company, 
                         current_year=current_year,
                         monthly_tax_data=monthly_tax_data,
                         annual_summary=annual_summary,
                         chart_data=chart_data)

@movements_bp.route('/companies/<int:company_id>/taxes/payment', methods=['POST'])
@login_required
@require_company_perm('taxes')
def record_tax_payment(company_id):
    """Registrar pago de impuestos manual"""
    company = Company.query.get_or_404(company_id)
    
    try:
        month = int(request.form.get('month'))
        year = int(request.form.get('year'))
        amount = float(request.form.get('amount'))
        tax_type = request.form.get('tax_type', 'IVA')
        notes = request.form.get('notes')
        
        payment = TaxPayment(
            company_id=company_id,
            period_month=month,
            period_year=year,
            tax_type=tax_type,
            amount=amount,
            notes=notes,
            payment_date=now_mexico()
        )
        
        db.session.add(payment)
        db.session.commit()
        
        flash('Pago de impuestos registrado correctamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar pago: {str(e)}', 'error')
        
    return redirect(url_for('movements.taxes_dashboard', company_id=company_id))

