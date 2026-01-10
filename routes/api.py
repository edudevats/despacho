"""
API routes - JSON endpoints for AJAX and integrations.
"""

import logging
from datetime import datetime
from utils.timezone_helper import now_mexico
from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy import func, extract
from extensions import db, cache
from models import Company, Movement

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


@api_bp.route('/companies/<int:company_id>/stats')
@login_required
@cache.cached(timeout=60, query_string=True)
def company_stats(company_id):
    """API endpoint para estadísticas en tiempo real (cached 60s)."""
    company = Company.query.get_or_404(company_id)
    
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    
    if not month or not year:
        today = now_mexico()
        month = today.month
        year = today.year
    
    income = db.session.query(func.sum(Movement.amount)).filter(
        Movement.company_id == company_id,
        Movement.type == 'INCOME',
        extract('month', Movement.date) == month,
        extract('year', Movement.date) == year
    ).scalar() or 0
    
    expense = db.session.query(func.sum(Movement.amount)).filter(
        Movement.company_id == company_id,
        Movement.type == 'EXPENSE',
        extract('month', Movement.date) == month,
        extract('year', Movement.date) == year
    ).scalar() or 0
    
    return jsonify({
        'company_id': company_id,
        'company_name': company.name,
        'income': float(income),
        'expense': float(expense),
        'balance': float(income - expense),
        'month': month,
        'year': year
    })


@api_bp.route('/companies/<int:company_id>/monthly-stats')
@login_required
@cache.cached(timeout=300, query_string=True)
def company_monthly_stats(company_id):
    """Get all monthly statistics for a company in one call."""
    company = Company.query.get_or_404(company_id)
    
    year = request.args.get('year', type=int) or now_mexico().year
    
    # Optimized single query for all months
    stats = db.session.query(
        extract('month', Movement.date).label('month'),
        Movement.type,
        func.sum(Movement.amount).label('total')
    ).filter(
        Movement.company_id == company_id,
        extract('year', Movement.date) == year
    ).group_by('month', Movement.type).all()
    
    # Organize by month
    monthly_data = {i: {'income': 0, 'expense': 0} for i in range(1, 13)}
    for row in stats:
        month = int(row.month) if row.month else 0
        if month in monthly_data:
            if row.type == 'INCOME':
                monthly_data[month]['income'] = float(row.total or 0)
            elif row.type == 'EXPENSE':
                monthly_data[month]['expense'] = float(row.total or 0)
    
    # Format response
    month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                   'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    
    result = []
    for month_num in range(1, 13):
        data = monthly_data[month_num]
        result.append({
            'month': month_num,
            'month_name': month_names[month_num - 1],
            'income': data['income'],
            'expense': data['expense'],
            'balance': data['income'] - data['expense']
        })
    
    return jsonify({
        'company_id': company_id,
        'year': year,
        'data': result
    })


@api_bp.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Test database connection
        db.session.execute(db.text('SELECT 1'))
        db_status = 'healthy'
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = 'unhealthy'
    
    return jsonify({
        'status': 'healthy' if db_status == 'healthy' else 'degraded',
        'database': db_status,
        'timestamp': now_mexico().isoformat()
    })
