"""
Mobile API routes - JSON endpoints for Flutter/Android app.
Uses JWT token authentication instead of session cookies.
"""

import logging
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import Blueprint, jsonify, request, current_app
from werkzeug.security import check_password_hash
from sqlalchemy import func, extract

from extensions import db
from models import (
    User, Company, UserCompanyAccess, Movement, Product, ProductBatch,
    Invoice
)
from utils.timezone_helper import now_mexico

logger = logging.getLogger(__name__)

mobile_api_bp = Blueprint('mobile_api', __name__)


# --- CORS support for mobile app ---

@mobile_api_bp.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


@mobile_api_bp.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        return '', 204


# --- JWT helpers ---

def create_token(user_id):
    """Create a JWT token for a user."""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(
            hours=current_app.config.get('JWT_EXPIRATION_HOURS', 72)
        ),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )


def token_required(f):
    """Decorator to require a valid JWT token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Token requerido'}), 401

        token = auth_header.split(' ', 1)[1]
        try:
            payload = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=['HS256']
            )
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido'}), 401

        user = db.session.get(User, payload['user_id'])
        if not user or not user.is_active:
            return jsonify({'error': 'Usuario no encontrado o inactivo'}), 401

        kwargs['current_user'] = user
        return f(*args, **kwargs)
    return decorated


# --- Endpoints ---

@mobile_api_bp.route('/login', methods=['POST'])
def mobile_login():
    """Authenticate user and return JWT token."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON con username y password'}), 400

    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña son requeridos'}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        logger.warning(f"Mobile: failed login attempt for '{username}'")
        return jsonify({'error': 'Usuario o contraseña incorrectos'}), 401

    if not user.is_active:
        return jsonify({'error': 'Cuenta desactivada'}), 403

    token = create_token(user.id)
    logger.info(f"Mobile: user '{username}' logged in")

    return jsonify({
        'token': token,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin,
        }
    })


@mobile_api_bp.route('/me', methods=['GET'])
@token_required
def mobile_me(current_user):
    """Return current user info."""
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'is_admin': current_user.is_admin,
    })


@mobile_api_bp.route('/companies', methods=['GET'])
@token_required
def mobile_companies(current_user):
    """List companies accessible to the user."""
    companies = current_user.get_accessible_companies()

    result = []
    for c in companies:
        permissions = current_user.get_company_permissions(c.id)
        result.append({
            'id': c.id,
            'rfc': c.rfc,
            'name': c.name,
            'postal_code': c.postal_code,
            'has_logo': bool(c.logo_path),
            'permissions': permissions,
        })

    return jsonify({'companies': result})


@mobile_api_bp.route('/companies/<int:company_id>/stats', methods=['GET'])
@token_required
def mobile_company_stats(company_id, current_user):
    """Monthly income/expense stats for a company."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    company = db.session.get(Company, company_id)
    if not company:
        return jsonify({'error': 'Empresa no encontrada'}), 404

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

    # Count invoices
    invoice_count = Invoice.query.filter(
        Invoice.company_id == company_id,
        extract('month', Invoice.date) == month,
        extract('year', Invoice.date) == year
    ).count()

    return jsonify({
        'company_id': company_id,
        'company_name': company.name,
        'income': float(income),
        'expense': float(expense),
        'balance': float(income - expense),
        'invoice_count': invoice_count,
        'month': month,
        'year': year,
    })


@mobile_api_bp.route('/companies/<int:company_id>/monthly-stats', methods=['GET'])
@token_required
def mobile_monthly_stats(company_id, current_user):
    """Full year monthly breakdown for a company."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    company = db.session.get(Company, company_id)
    if not company:
        return jsonify({'error': 'Empresa no encontrada'}), 404

    year = request.args.get('year', type=int) or now_mexico().year

    stats = db.session.query(
        extract('month', Movement.date).label('month'),
        Movement.type,
        func.sum(Movement.amount).label('total')
    ).filter(
        Movement.company_id == company_id,
        extract('year', Movement.date) == year
    ).group_by('month', Movement.type).all()

    monthly_data = {i: {'income': 0, 'expense': 0} for i in range(1, 13)}
    for row in stats:
        m = int(row.month) if row.month else 0
        if m in monthly_data:
            if row.type == 'INCOME':
                monthly_data[m]['income'] = float(row.total or 0)
            elif row.type == 'EXPENSE':
                monthly_data[m]['expense'] = float(row.total or 0)

    month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                   'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

    result = []
    for num in range(1, 13):
        d = monthly_data[num]
        result.append({
            'month': num,
            'month_name': month_names[num - 1],
            'income': d['income'],
            'expense': d['expense'],
            'balance': d['income'] - d['expense'],
        })

    return jsonify({
        'company_id': company_id,
        'year': year,
        'data': result,
    })


@mobile_api_bp.route('/companies/<int:company_id>/products', methods=['GET'])
@token_required
def mobile_products(company_id, current_user):
    """List products/inventory for a company."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    search = request.args.get('q', '').strip()
    low_stock = request.args.get('low_stock', type=int)  # 1 = only low stock

    query = Product.query.filter_by(company_id=company_id, active=True)

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
                Product.active_ingredient.ilike(f'%{search}%'),
            )
        )

    if low_stock:
        query = query.filter(Product.current_stock <= Product.min_stock_level)

    products = query.order_by(Product.name).all()

    result = []
    for p in products:
        result.append({
            'id': p.id,
            'sku': p.sku,
            'name': p.name,
            'description': p.description,
            'current_stock': p.current_stock,
            'min_stock_level': p.min_stock_level,
            'low_stock': p.current_stock <= p.min_stock_level,
            'cost_price': p.cost_price,
            'selling_price': p.calculated_selling_price,
            'unit_measure': p.unit_measure,
            'active_ingredient': p.active_ingredient,
            'presentation': p.presentation,
            'is_controlled': p.is_controlled,
        })

    return jsonify({'products': result, 'count': len(result)})


@mobile_api_bp.route('/companies/<int:company_id>/products/<int:product_id>', methods=['GET'])
@token_required
def mobile_product_detail(company_id, product_id, current_user):
    """Product detail with batches."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    product = Product.query.filter_by(
        id=product_id, company_id=company_id
    ).first()

    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404

    batches = ProductBatch.query.filter_by(
        product_id=product_id, is_active=True
    ).order_by(ProductBatch.expiration_date.asc()).all()

    batch_list = []
    for b in batches:
        batch_list.append({
            'id': b.id,
            'batch_number': b.batch_number,
            'expiration_date': b.expiration_date.isoformat() if b.expiration_date else None,
            'current_stock': b.current_stock,
            'initial_stock': b.initial_stock,
        })

    return jsonify({
        'product': {
            'id': product.id,
            'sku': product.sku,
            'name': product.name,
            'description': product.description,
            'current_stock': product.current_stock,
            'min_stock_level': product.min_stock_level,
            'cost_price': product.cost_price,
            'selling_price': product.calculated_selling_price,
            'profit_margin': product.profit_margin,
            'unit_measure': product.unit_measure,
            'active_ingredient': product.active_ingredient,
            'presentation': product.presentation,
            'therapeutic_group': product.therapeutic_group,
            'is_controlled': product.is_controlled,
            'sanitary_registration': product.sanitary_registration,
            'laboratory': product.laboratory.name if product.laboratory else None,
            'preferred_supplier': product.preferred_supplier.business_name if product.preferred_supplier else None,
        },
        'batches': batch_list,
    })
