"""
Tax management routes - Dashboard, payments, calculations.
"""

import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func, extract
from extensions import db
from models import Company, Invoice, TaxPayment

logger = logging.getLogger(__name__)

taxes_bp = Blueprint('taxes', __name__)


@taxes_bp.route('/taxes')
@login_required
def taxes_list():
    """Show list of companies for tax calculations."""
    companies_list = Company.query.all()
    return render_template('taxes_list.html', companies=companies_list)


@taxes_bp.route('/companies/<int:company_id>/taxes')
@login_required
def taxes_dashboard(company_id):
    """Dashboard de Impuestos con IVA, ISR y resumen anual."""
    company = Company.query.get_or_404(company_id)
    
    today = datetime.now()
    current_year = today.year
    
    # Calculate monthly tax data
    monthly_tax_data = []
    month_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    # Optimized query - get all data in one query grouped by month and type
    invoice_stats = db.session.query(
        extract('month', Invoice.date).label('month'),
        Invoice.type,
        func.sum(Invoice.tax).label('total_tax'),
        func.sum(Invoice.subtotal).label('total_subtotal')
    ).filter(
        Invoice.company_id == company_id,
        extract('year', Invoice.date) == current_year
    ).group_by('month', Invoice.type).all()
    
    # Organize data by month
    monthly_invoice_data = {}
    for row in invoice_stats:
        month = int(row.month) if row.month else 0
        if month not in monthly_invoice_data:
            monthly_invoice_data[month] = {'I': {'tax': 0, 'subtotal': 0}, 'E': {'tax': 0, 'subtotal': 0}}
        if row.type in ['I', 'E']:
            monthly_invoice_data[month][row.type] = {
                'tax': float(row.total_tax or 0),
                'subtotal': float(row.total_subtotal or 0)
            }
    
    # Get all tax payments for the year in one query
    tax_payments = TaxPayment.query.filter(
        TaxPayment.company_id == company_id,
        TaxPayment.period_year == current_year
    ).all()
    
    # Organize payments by month and type
    payments_by_month = {}
    for payment in tax_payments:
        key = (payment.period_month, payment.tax_type)
        if key not in payments_by_month:
            payments_by_month[key] = 0
        payments_by_month[key] += payment.amount
    
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
        data = monthly_invoice_data.get(month_num, {'I': {'tax': 0, 'subtotal': 0}, 'E': {'tax': 0, 'subtotal': 0}})
        
        iva_collected = data['I']['tax']
        iva_deductible = data['E']['tax']
        month_income = data['I']['subtotal']
        month_expense = data['E']['subtotal']
        
        # Net IVA Position
        net_iva = iva_collected - iva_deductible
        
        # ISR Estimado (30% de utilidad bruta, solo si es positiva)
        profit = month_income - month_expense
        isr_estimated = max(0, profit * 0.30)
        
        # Get payments from pre-fetched data
        iva_paid_amount = payments_by_month.get((month_num, 'IVA'), 0)
        isr_paid_amount = payments_by_month.get((month_num, 'ISR'), 0)
        
        # Accumulate annual totals
        if net_iva > 0:
            annual_iva_to_pay += net_iva
        annual_iva_paid += iva_paid_amount
        annual_isr_estimated += isr_estimated
        annual_isr_paid += isr_paid_amount
        annual_income += month_income
        annual_expense += month_expense
        
        # Chart data
        chart_months.append(month_names[month_num - 1][:3])
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


@taxes_bp.route('/companies/<int:company_id>/taxes/payment', methods=['POST'])
@login_required
def record_tax_payment(company_id):
    """Registrar pago de impuestos manual."""
    company = Company.query.get_or_404(company_id)
    
    try:
        month = int(request.form.get('month'))
        year = int(request.form.get('year'))
        amount = float(request.form.get('amount'))
        tax_type = request.form.get('tax_type', 'IVA')
        notes = request.form.get('notes')
        
        if amount <= 0:
            flash('El monto debe ser mayor a cero.', 'error')
            return redirect(url_for('taxes.taxes_dashboard', company_id=company_id))
        
        payment = TaxPayment(
            company_id=company_id,
            period_month=month,
            period_year=year,
            tax_type=tax_type,
            amount=amount,
            notes=notes,
            payment_date=datetime.now()
        )
        
        db.session.add(payment)
        db.session.commit()
        
        logger.info(f"Tax payment recorded: {tax_type} ${amount} for {company.name} ({month}/{year})")
        flash('Pago de impuestos registrado correctamente', 'success')
        
    except ValueError as e:
        flash('Datos inválidos. Verifica los campos.', 'error')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error recording tax payment: {e}")
        flash(f'Error al registrar pago: {str(e)}', 'error')
    
    return redirect(url_for('taxes.taxes_dashboard', company_id=company_id))
