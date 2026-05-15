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


main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def index():
    # Get all companies for selector
    companies = Company.query.all()
    
    # Get selected company from query parameter
    company_id = request.args.get('company_id', type=int)
    selected_company = None
    if company_id:
        selected_company = db.session.get(Company, company_id)
    
    # Get current year for filtering
    today = now_mexico()
    current_year = today.year
    
    # Get selected year from query parameter, default to current year
    selected_year = request.args.get('year', type=int, default=current_year)
    
    # Base queries - filter by selected year
    income_query = db.session.query(db.func.sum(Movement.amount)).filter(
        Movement.type == 'INCOME',
        extract('year', Movement.date) == selected_year
    )
    expenses_query = db.session.query(db.func.sum(Movement.amount)).filter(
        Movement.type == 'EXPENSE',
        extract('year', Movement.date) == selected_year
    )
    
    # Apply company filter if selected
    if company_id:
        income_query = income_query.filter(Movement.company_id == company_id)
        expenses_query = expenses_query.filter(Movement.company_id == company_id)
    
    # Calculate totals for current year
    income = income_query.scalar() or 0
    expenses = expenses_query.scalar() or 0
    
    # Calculate monthly statistics for selected year
    current_month = today.month
    monthly_data = []
    month_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    # Calculate all 12 months for the selected year
    for month_num in range(1, 13):
        # Only include months up to current month if viewing current year
        if selected_year == current_year and month_num > current_month:
            continue
            
        # Income for this month
        month_income_query = db.session.query(func.sum(Movement.amount)).filter(
            Movement.type == 'INCOME',
            extract('month', Movement.date) == month_num,
            extract('year', Movement.date) == selected_year
        )
        
        # Expenses for this month
        month_expense_query = db.session.query(func.sum(Movement.amount)).filter(
            Movement.type == 'EXPENSE',
            extract('month', Movement.date) == month_num,
            extract('year', Movement.date) == selected_year
        )
        
        # Apply company filter
        if company_id:
            month_income_query = month_income_query.filter(Movement.company_id == company_id)
            month_expense_query = month_expense_query.filter(Movement.company_id == company_id)
        
        month_income = month_income_query.scalar() or 0
        month_expense = month_expense_query.scalar() or 0
        
        monthly_data.append({
            'month': month_names[month_num - 1],
            'income': float(month_income),
            'expenses': float(month_expense),
            'balance': float(month_income - month_expense)
        })
    
    # Calculate annual statistics for selected year
    annual_income_query = db.session.query(func.sum(Movement.amount)).filter(
        Movement.type == 'INCOME',
        extract('year', Movement.date) == selected_year
    )
    annual_expense_query = db.session.query(func.sum(Movement.amount)).filter(
        Movement.type == 'EXPENSE',
        extract('year', Movement.date) == selected_year
    )
    
    if company_id:
        annual_income_query = annual_income_query.filter(Movement.company_id == company_id)
        annual_expense_query = annual_expense_query.filter(Movement.company_id == company_id)
    
    annual_income = annual_income_query.scalar() or 0
    annual_expense = annual_expense_query.scalar() or 0
    
    # Calculate Inventory Value (Cost Price)
    inventory_query = db.session.query(
        func.sum(Product.current_stock * Product.cost_price)
    ).filter(Product.active == True)
    
    if company_id:
        inventory_query = inventory_query.filter(Product.company_id == company_id)
        
    inventory_value = inventory_query.scalar() or 0
    
    # Get available years from movements
    years_query = db.session.query(
        extract('year', Movement.date).label('year')
    ).distinct().order_by(extract('year', Movement.date).desc())
    
    if company_id:
        years_query = years_query.filter(Movement.company_id == company_id)
    
    available_years = [int(year[0]) for year in years_query.all() if year[0]]
    if not available_years:
        available_years = [current_year]
    
    return render_template('dashboard.html',
        companies=companies,
        selected_company=selected_company,
        income=income,
        expenses=expenses,
        inventory_value=inventory_value,
        monthly_data=monthly_data,
        selected_year=selected_year,
        available_years=available_years,
        current_year=current_year,
        annual_stats={
            'year': selected_year,
            'income': float(annual_income),
            'expenses': float(annual_expense),
            'balance': float(annual_income - annual_expense)
        }
    )

