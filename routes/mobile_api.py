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
    Invoice, ExitOrder, ExitOrderDetail, InventoryTransaction
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


# ==================== POS / SCANNER ENDPOINTS ====================


def _serialize_exit_order(order):
    """Serialize an ExitOrder to dict."""
    items = []
    for d in order.details:
        items.append({
            'id': d.id,
            'product_id': d.product_id,
            'product_name': d.product.name if d.product else None,
            'product_sku': d.product.sku if d.product else None,
            'batch_id': d.batch_id,
            'batch_number': d.batch.batch_number if d.batch else None,
            'expiration_date': d.batch.expiration_date.isoformat() if d.batch and d.batch.expiration_date else None,
            'quantity': d.quantity,
            'scanned_at': d.scanned_at.isoformat() if d.scanned_at else None,
            'scanned_by': d.scanned_by.username if d.scanned_by else None,
        })
    return {
        'id': order.id,
        'company_id': order.company_id,
        'recipient_name': order.recipient_name,
        'recipient_type': order.recipient_type,
        'recipient_id': order.recipient_id,
        'status': order.status,
        'notes': order.notes,
        'total_items': order.total_items,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'completed_at': order.completed_at.isoformat() if order.completed_at else None,
        'created_by': order.created_by.username if order.created_by else None,
        'items': items,
    }


@mobile_api_bp.route('/pos/exit-orders', methods=['POST'])
@token_required
def pos_create_exit_order(current_user):
    """Create a new ExitOrder in DRAFT status."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON'}), 400

    company_id = data.get('company_id')
    if not company_id or not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    recipient_name = (data.get('recipient_name') or '').strip()
    if not recipient_name:
        return jsonify({'error': 'Nombre del destinatario es requerido'}), 400

    order = ExitOrder(
        company_id=company_id,
        recipient_name=recipient_name,
        recipient_type=data.get('recipient_type', 'PATIENT'),
        recipient_id=data.get('recipient_id'),
        notes=data.get('notes'),
        created_by_id=current_user.id,
    )
    db.session.add(order)
    db.session.commit()

    logger.info(f"POS: user '{current_user.username}' created ExitOrder #{order.id}")
    return jsonify(_serialize_exit_order(order)), 201


@mobile_api_bp.route('/pos/exit-orders', methods=['GET'])
@token_required
def pos_list_exit_orders(current_user):
    """List recent exit orders for a company."""
    company_id = request.args.get('company_id', type=int)
    if not company_id or not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    status_filter = request.args.get('status')  # DRAFT, COMPLETED, or omit for all

    query = ExitOrder.query.filter_by(company_id=company_id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    orders = query.order_by(ExitOrder.created_at.desc()).limit(50).all()

    result = []
    for o in orders:
        result.append({
            'id': o.id,
            'recipient_name': o.recipient_name,
            'recipient_type': o.recipient_type,
            'status': o.status,
            'total_items': o.total_items,
            'created_at': o.created_at.isoformat() if o.created_at else None,
            'completed_at': o.completed_at.isoformat() if o.completed_at else None,
            'created_by': o.created_by.username if o.created_by else None,
        })

    return jsonify({'orders': result})


@mobile_api_bp.route('/pos/exit-orders/<int:order_id>', methods=['GET'])
@token_required
def pos_get_exit_order(order_id, current_user):
    """Get exit order detail with all items."""
    order = db.session.get(ExitOrder, order_id)
    if not order:
        return jsonify({'error': 'Orden no encontrada'}), 404
    if not current_user.can_access_company(order.company_id):
        return jsonify({'error': 'Sin acceso'}), 403

    return jsonify(_serialize_exit_order(order))


@mobile_api_bp.route('/pos/scan', methods=['POST'])
@token_required
def pos_scan(current_user):
    """
    Scan a barcode: lookup product, auto-select FEFO batch, add to order.

    Input: {"barcode": "7501234567890", "exit_order_id": 22}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON'}), 400

    barcode = (data.get('barcode') or '').strip()
    order_id = data.get('exit_order_id')

    if not barcode or not order_id:
        return jsonify({'error': 'barcode y exit_order_id son requeridos'}), 400

    # Validate order
    order = db.session.get(ExitOrder, order_id)
    if not order:
        return jsonify({'error': 'Orden no encontrada'}), 404
    if not current_user.can_access_company(order.company_id):
        return jsonify({'error': 'Sin acceso'}), 403
    if order.status != 'DRAFT':
        return jsonify({'error': 'La orden ya fue completada', 'allowed': False}), 400

    # Find product by SKU (barcode)
    product = Product.query.filter(
        Product.company_id == order.company_id,
        Product.active == True,
        db.func.lower(Product.sku) == barcode.lower()
    ).first()

    if not product:
        return jsonify({
            'allowed': False,
            'error': f'Producto no encontrado para código: {barcode}',
            'alert': 'NO_ENCONTRADO',
        }), 404

    # FEFO: find best batch (earliest expiration, with stock, not expired)
    today = now_mexico().date()

    batch = ProductBatch.query.filter(
        ProductBatch.product_id == product.id,
        ProductBatch.current_stock > 0,
        ProductBatch.is_active == True,
        ProductBatch.expiration_date != None,
        ProductBatch.expiration_date >= today,
    ).order_by(ProductBatch.expiration_date.asc()).first()

    # Also try batches without expiration date (no expiry tracking)
    if not batch:
        batch = ProductBatch.query.filter(
            ProductBatch.product_id == product.id,
            ProductBatch.current_stock > 0,
            ProductBatch.is_active == True,
            ProductBatch.expiration_date == None,
        ).first()

    # Check if product has stock at all (even without batches)
    if not batch and product.current_stock <= 0:
        return jsonify({
            'allowed': False,
            'error': f'Sin stock disponible para {product.name}',
            'alert': 'SIN_STOCK',
            'product': {'id': product.id, 'name': product.name, 'sku': product.sku},
        }), 400

    # Determine expiration alert
    alert = None
    days_to_expire = None
    if batch and batch.expiration_date:
        delta = (batch.expiration_date - today).days
        days_to_expire = delta
        if delta <= 0:
            # Should not happen due to filter, but safety check
            return jsonify({
                'allowed': False,
                'error': f'Lote {batch.batch_number} EXPIRADO',
                'alert': 'EXPIRADO',
                'product': {'id': product.id, 'name': product.name, 'sku': product.sku},
            }), 400
        elif delta <= 30:
            alert = 'CRITICO'
        elif delta <= 90:
            alert = 'PROXIMO'

    # Check if same product+batch already in this order → increment qty
    existing_detail = ExitOrderDetail.query.filter_by(
        order_id=order.id,
        product_id=product.id,
        batch_id=batch.id if batch else None,
    ).first()

    if existing_detail:
        existing_detail.quantity += 1
        detail = existing_detail
    else:
        detail = ExitOrderDetail(
            order_id=order.id,
            product_id=product.id,
            batch_id=batch.id if batch else None,
            quantity=1,
            scanned_at=now_mexico(),
            scanned_by_id=current_user.id,
        )
        db.session.add(detail)

    db.session.commit()

    # Calculate order total
    order_total = sum(d.quantity for d in order.details)

    logger.info(
        f"POS: scan '{barcode}' → {product.name} "
        f"batch={batch.batch_number if batch else 'N/A'} "
        f"order=#{order.id} user={current_user.username}"
    )

    return jsonify({
        'allowed': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
            'active_ingredient': product.active_ingredient,
            'presentation': product.presentation,
            'is_controlled': product.is_controlled,
        },
        'batch': {
            'id': batch.id if batch else None,
            'batch_number': batch.batch_number if batch else None,
            'expiration_date': batch.expiration_date.isoformat() if batch and batch.expiration_date else None,
            'current_stock': batch.current_stock if batch else product.current_stock,
        },
        'alert': alert,
        'days_to_expire': days_to_expire,
        'detail_id': detail.id,
        'quantity': detail.quantity,
        'order_total_items': order_total,
    })


@mobile_api_bp.route('/pos/lookup', methods=['POST'])
@token_required
def pos_lookup(current_user):
    """Lookup a product by barcode without adding to any order."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON'}), 400

    barcode = (data.get('barcode') or '').strip()
    company_id = data.get('company_id')

    if not barcode or not company_id:
        return jsonify({'error': 'barcode y company_id son requeridos'}), 400

    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso'}), 403

    product = Product.query.filter(
        Product.company_id == company_id,
        Product.active == True,
        db.func.lower(Product.sku) == barcode.lower()
    ).first()

    if not product:
        return jsonify({'found': False, 'error': 'Producto no encontrado'}), 404

    today = now_mexico().date()
    batches = ProductBatch.query.filter(
        ProductBatch.product_id == product.id,
        ProductBatch.current_stock > 0,
        ProductBatch.is_active == True,
    ).order_by(ProductBatch.expiration_date.asc()).all()

    batch_list = []
    for b in batches:
        days = None
        batch_alert = None
        if b.expiration_date:
            days = (b.expiration_date - today).days
            if days <= 0:
                batch_alert = 'EXPIRADO'
            elif days <= 30:
                batch_alert = 'CRITICO'
            elif days <= 90:
                batch_alert = 'PROXIMO'
        batch_list.append({
            'id': b.id,
            'batch_number': b.batch_number,
            'expiration_date': b.expiration_date.isoformat() if b.expiration_date else None,
            'current_stock': b.current_stock,
            'days_to_expire': days,
            'alert': batch_alert,
        })

    return jsonify({
        'found': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
            'current_stock': product.current_stock,
            'active_ingredient': product.active_ingredient,
            'presentation': product.presentation,
            'is_controlled': product.is_controlled,
        },
        'batches': batch_list,
    })


@mobile_api_bp.route('/pos/exit-orders/<int:order_id>/remove-item', methods=['POST'])
@token_required
def pos_remove_item(order_id, current_user):
    """Remove an item from a DRAFT exit order."""
    data = request.get_json(silent=True)
    detail_id = data.get('detail_id') if data else None
    if not detail_id:
        return jsonify({'error': 'detail_id es requerido'}), 400

    order = db.session.get(ExitOrder, order_id)
    if not order:
        return jsonify({'error': 'Orden no encontrada'}), 404
    if not current_user.can_access_company(order.company_id):
        return jsonify({'error': 'Sin acceso'}), 403
    if order.status != 'DRAFT':
        return jsonify({'error': 'No se puede modificar una orden completada'}), 400

    detail = db.session.get(ExitOrderDetail, detail_id)
    if not detail or detail.order_id != order.id:
        return jsonify({'error': 'Item no encontrado en esta orden'}), 404

    db.session.delete(detail)
    db.session.commit()

    order_total = sum(d.quantity for d in order.details)
    return jsonify({'success': True, 'order_total_items': order_total})


@mobile_api_bp.route('/pos/exit-orders/<int:order_id>/complete', methods=['POST'])
@token_required
def pos_complete_exit_order(order_id, current_user):
    """
    Complete an exit order: validate stock, deduct inventory, create transactions.
    This is the ONLY point where inventory is modified.
    """
    order = db.session.get(ExitOrder, order_id)
    if not order:
        return jsonify({'error': 'Orden no encontrada'}), 404
    if not current_user.can_access_company(order.company_id):
        return jsonify({'error': 'Sin acceso'}), 403
    if order.status != 'DRAFT':
        return jsonify({'error': 'Esta orden ya fue procesada'}), 400
    if not order.details:
        return jsonify({'error': 'No hay productos en la orden'}), 400

    # Validate stock for ALL items before processing any
    errors = []
    for detail in order.details:
        if detail.quantity > detail.product.current_stock:
            errors.append(
                f'{detail.product.name}: stock insuficiente '
                f'(necesita {detail.quantity}, disponible {detail.product.current_stock})'
            )
        if detail.batch and detail.quantity > detail.batch.current_stock:
            errors.append(
                f'{detail.product.name} lote {detail.batch.batch_number}: '
                f'stock insuficiente en lote '
                f'(necesita {detail.quantity}, disponible {detail.batch.current_stock})'
            )

    if errors:
        return jsonify({'error': 'Stock insuficiente', 'details': errors}), 400

    # Process each detail: create transactions and deduct inventory
    for detail in order.details:
        product = detail.product
        previous_stock = product.current_stock

        transaction = InventoryTransaction(
            product_id=product.id,
            batch_id=detail.batch_id,
            type='OUT',
            quantity=detail.quantity,
            previous_stock=previous_stock,
            new_stock=previous_stock - detail.quantity,
            reference=f'Orden Salida #{order.id} (POS)',
            notes=f'Entrega a: {order.recipient_name} | Escaneado por: {detail.scanned_by.username if detail.scanned_by else "N/A"}',
        )
        db.session.add(transaction)

        product.current_stock -= detail.quantity

        if detail.batch_id and detail.batch:
            detail.batch.current_stock -= detail.quantity
            if detail.batch.current_stock <= 0:
                detail.batch.is_active = False

    order.status = 'COMPLETED'
    order.completed_at = now_mexico()
    db.session.commit()

    logger.info(
        f"POS: ExitOrder #{order.id} COMPLETED by '{current_user.username}' "
        f"({order.total_items} items to '{order.recipient_name}')"
    )

    return jsonify({
        'success': True,
        'order': _serialize_exit_order(order),
    })
