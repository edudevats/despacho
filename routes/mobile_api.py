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
    Invoice, ExitOrder, ExitOrderDetail, InventoryTransaction,
    PurchaseOrder, PurchaseOrderDetail, Supplier
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


# ==================== PURCHASE ORDERS / ENTRADA ENDPOINTS ====================


def _serialize_purchase_order(order, include_items=True):
    """Serialize a PurchaseOrder to dict."""
    data = {
        'id': order.id,
        'company_id': order.company_id,
        'supplier_id': order.supplier_id,
        'supplier_name': order.supplier.business_name if order.supplier else None,
        'status': order.status,
        'estimated_total': order.estimated_total or 0,
        'notes': order.notes,
        'total_items': len(order.details),
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'sent_at': order.sent_at.isoformat() if order.sent_at else None,
        'received_at': order.received_at.isoformat() if order.received_at else None,
        'completed_at': order.completed_at.isoformat() if order.completed_at else None,
    }
    if include_items:
        items = []
        for d in order.details:
            items.append({
                'id': d.id,
                'product_id': d.product_id,
                'product_name': d.product.name if d.product else None,
                'product_sku': d.product.sku if d.product else None,
                'quantity_requested': d.quantity_requested,
                'quantity_received': d.quantity_received,
                'unit_cost': d.unit_cost,
                'batch_number': d.batch_number,
                'expiration_date': d.expiration_date.isoformat() if d.expiration_date else None,
            })
        data['items'] = items
    return data


@mobile_api_bp.route('/companies/<int:company_id>/suppliers', methods=['GET'])
@token_required
def mobile_suppliers(company_id, current_user):
    """List active suppliers for a company."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    search = request.args.get('q', '').strip()

    query = Supplier.query.filter_by(company_id=company_id, active=True)

    if search:
        query = query.filter(
            db.or_(
                Supplier.business_name.ilike(f'%{search}%'),
                Supplier.rfc.ilike(f'%{search}%'),
                Supplier.commercial_name.ilike(f'%{search}%'),
            )
        )

    suppliers = query.order_by(Supplier.business_name).all()

    result = []
    for s in suppliers:
        result.append({
            'id': s.id,
            'rfc': s.rfc,
            'business_name': s.business_name,
            'commercial_name': s.commercial_name,
            'contact_name': s.contact_name,
            'email': s.email,
            'phone': s.phone,
            'is_medication_supplier': s.is_medication_supplier,
            'sanitary_registration': s.sanitary_registration,
        })

    return jsonify({'suppliers': result})


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders', methods=['GET'])
@token_required
def mobile_list_purchase_orders(company_id, current_user):
    """List purchase orders for a company."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    status_filter = request.args.get('status')

    query = PurchaseOrder.query.filter_by(company_id=company_id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    orders = query.order_by(PurchaseOrder.created_at.desc()).limit(50).all()

    result = []
    for o in orders:
        result.append(_serialize_purchase_order(o, include_items=False))

    return jsonify({'orders': result})


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders/<int:order_id>', methods=['GET'])
@token_required
def mobile_get_purchase_order(company_id, order_id, current_user):
    """Get purchase order detail with all items."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    order = db.session.get(PurchaseOrder, order_id)
    if not order or order.company_id != company_id:
        return jsonify({'error': 'Orden no encontrada'}), 404

    return jsonify(_serialize_purchase_order(order))


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders', methods=['POST'])
@token_required
def mobile_create_purchase_order(company_id, current_user):
    """Create a new purchase order in DRAFT status."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON'}), 400

    supplier_id = data.get('supplier_id')
    if not supplier_id:
        return jsonify({'error': 'supplier_id es requerido'}), 400

    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id, active=True).first()
    if not supplier:
        return jsonify({'error': 'Proveedor no encontrado'}), 404

    order = PurchaseOrder(
        company_id=company_id,
        supplier_id=supplier_id,
        status='DRAFT',
        notes=data.get('notes'),
    )
    db.session.add(order)
    db.session.commit()

    logger.info(f"Mobile: user '{current_user.username}' created PurchaseOrder #{order.id}")
    return jsonify(_serialize_purchase_order(order)), 201


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders/<int:order_id>/add-item', methods=['POST'])
@token_required
def mobile_add_purchase_order_item(company_id, order_id, current_user):
    """Add a product to a purchase order."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    order = db.session.get(PurchaseOrder, order_id)
    if not order or order.company_id != company_id:
        return jsonify({'error': 'Orden no encontrada'}), 404

    if order.status not in ['DRAFT', 'SENT']:
        return jsonify({'error': 'Esta orden no se puede editar'}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON'}), 400

    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    unit_cost = data.get('unit_cost', 0)

    if not product_id or quantity < 1:
        return jsonify({'error': 'product_id y quantity son requeridos'}), 400

    product = Product.query.filter_by(id=product_id, company_id=company_id, active=True).first()
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404

    detail = PurchaseOrderDetail(
        order_id=order.id,
        product_id=product_id,
        quantity_requested=quantity,
        unit_cost=unit_cost,
    )
    db.session.add(detail)

    # Recalculate estimated total
    order.estimated_total = sum(d.quantity_requested * d.unit_cost for d in order.details) + (quantity * unit_cost)
    db.session.commit()

    return jsonify(_serialize_purchase_order(order))


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders/<int:order_id>/remove-item', methods=['POST'])
@token_required
def mobile_remove_purchase_order_item(company_id, order_id, current_user):
    """Remove an item from a purchase order."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    order = db.session.get(PurchaseOrder, order_id)
    if not order or order.company_id != company_id:
        return jsonify({'error': 'Orden no encontrada'}), 404

    if order.status not in ['DRAFT', 'SENT']:
        return jsonify({'error': 'Esta orden no se puede editar'}), 400

    data = request.get_json(silent=True)
    detail_id = data.get('detail_id') if data else None
    if not detail_id:
        return jsonify({'error': 'detail_id es requerido'}), 400

    detail = db.session.get(PurchaseOrderDetail, detail_id)
    if not detail or detail.order_id != order.id:
        return jsonify({'error': 'Item no encontrado en esta orden'}), 404

    db.session.delete(detail)

    # Recalculate estimated total
    order.estimated_total = sum(d.quantity_requested * d.unit_cost for d in order.details if d.id != detail_id)
    db.session.commit()

    return jsonify({'success': True})


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders/<int:order_id>/send', methods=['POST'])
@token_required
def mobile_send_purchase_order(company_id, order_id, current_user):
    """Send a purchase order (DRAFT -> SENT)."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    order = db.session.get(PurchaseOrder, order_id)
    if not order or order.company_id != company_id:
        return jsonify({'error': 'Orden no encontrada'}), 404

    if order.status != 'DRAFT':
        return jsonify({'error': 'Solo se pueden enviar ordenes en borrador'}), 400

    if not order.details:
        return jsonify({'error': 'La orden no tiene productos'}), 400

    order.status = 'SENT'
    order.sent_at = now_mexico()
    db.session.commit()

    logger.info(f"Mobile: PurchaseOrder #{order.id} SENT by '{current_user.username}'")
    return jsonify(_serialize_purchase_order(order))


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders/<int:order_id>/review', methods=['POST'])
@token_required
def mobile_review_purchase_order(company_id, order_id, current_user):
    """Review/receive a purchase order - record received quantities, batches, expiration dates."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    order = db.session.get(PurchaseOrder, order_id)
    if not order or order.company_id != company_id:
        return jsonify({'error': 'Orden no encontrada'}), 404

    if order.status not in ['SENT', 'IN_REVIEW']:
        return jsonify({'error': 'Esta orden no puede ser revisada en este momento'}), 400

    data = request.get_json(silent=True)
    if not data or 'items' not in data:
        return jsonify({'error': 'Se requiere JSON con items'}), 400

    items_data = {item['detail_id']: item for item in data['items']}

    for detail in order.details:
        if detail.id in items_data:
            item = items_data[detail.id]
            detail.quantity_received = item.get('quantity_received', 0)
            detail.batch_number = item.get('batch_number') or None
            exp_str = item.get('expiration_date')
            if exp_str:
                detail.expiration_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            else:
                detail.expiration_date = None

    order.status = 'IN_REVIEW'
    order.received_at = now_mexico()
    db.session.commit()

    logger.info(f"Mobile: PurchaseOrder #{order.id} IN_REVIEW by '{current_user.username}'")
    return jsonify(_serialize_purchase_order(order))


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders/<int:order_id>/complete', methods=['POST'])
@token_required
def mobile_complete_purchase_order(company_id, order_id, current_user):
    """Complete a purchase order: create batches, transactions, update stock."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    order = db.session.get(PurchaseOrder, order_id)
    if not order or order.company_id != company_id:
        return jsonify({'error': 'Orden no encontrada'}), 404

    if order.status != 'IN_REVIEW':
        return jsonify({'error': 'Esta orden no puede ser completada en este momento'}), 400

    for detail in order.details:
        if detail.quantity_received > 0:
            product = detail.product
            previous_stock = product.current_stock
            batch_id = None

            # Create batch if batch info is present
            if detail.batch_number:
                batch = ProductBatch(
                    product_id=product.id,
                    batch_number=detail.batch_number,
                    expiration_date=detail.expiration_date,
                    initial_stock=detail.quantity_received,
                    current_stock=detail.quantity_received,
                    acquisition_date=now_mexico().date(),
                )
                db.session.add(batch)
                db.session.flush()
                batch_id = batch.id

            # Create inventory transaction
            transaction = InventoryTransaction(
                product_id=product.id,
                batch_id=batch_id,
                type='IN',
                quantity=detail.quantity_received,
                previous_stock=previous_stock,
                new_stock=previous_stock + detail.quantity_received,
                reference=f'Orden Compra #{order.id}',
                notes=f'Recepcion de orden de compra' + (f' - Lote: {detail.batch_number}' if detail.batch_number else ''),
            )
            db.session.add(transaction)

            # Update product stock
            product.current_stock += detail.quantity_received

    order.status = 'COMPLETED'
    order.completed_at = now_mexico()
    db.session.commit()

    logger.info(
        f"Mobile: PurchaseOrder #{order.id} COMPLETED by '{current_user.username}' "
        f"({len(order.details)} items)"
    )
    return jsonify({'success': True, 'order': _serialize_purchase_order(order)})


@mobile_api_bp.route('/companies/<int:company_id>/purchase-orders/<int:order_id>/delete', methods=['POST'])
@token_required
def mobile_delete_purchase_order(company_id, order_id, current_user):
    """Delete a draft purchase order."""
    if not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403

    order = db.session.get(PurchaseOrder, order_id)
    if not order or order.company_id != company_id:
        return jsonify({'error': 'Orden no encontrada'}), 404

    if order.status != 'DRAFT':
        return jsonify({'error': 'Solo se pueden eliminar ordenes en borrador'}), 400

    for detail in order.details:
        db.session.delete(detail)
    db.session.delete(order)
    db.session.commit()

    logger.info(f"Mobile: PurchaseOrder #{order_id} DELETED by '{current_user.username}'")
    return jsonify({'success': True})


# ==================== MEDICINE CATALOG ENDPOINTS ====================


@mobile_api_bp.route('/catalog/lookup-barcode', methods=['POST'])
@token_required
def catalog_lookup_barcode(current_user):
    """
    Hybrid barcode lookup: searches local catalog first, then external API.
    
    This is the main endpoint for the mobile app to scan a barcode and
    identify a medicine. It will:
    1. Search in local Product catalog by SKU
    2. If not found, query external barcode API (UPCitemdb, etc.)
    3. Return product information with suggestion to add to catalog
    
    Input: {"barcode": "7501234567890", "company_id": 1}
    """
    from services.barcode_service import get_barcode_service
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON'}), 400
    
    barcode = (data.get('barcode') or '').strip()
    company_id = data.get('company_id')
    
    if not barcode:
        return jsonify({'error': 'Código de barras es requerido'}), 400
    
    if not company_id or not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403
    
    # 1. Search in local catalog first
    product = Product.query.filter(
        Product.company_id == company_id,
        Product.active == True,
        db.func.lower(Product.sku) == barcode.lower()
    ).first()
    
    if product:
        # Found in local catalog
        logger.info(f"Catalog: barcode '{barcode}' found in local catalog (product #{product.id})")
        return jsonify({
            'found': True,
            'source': 'local',
            'product': {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'description': product.description,
                'active_ingredient': product.active_ingredient,
                'presentation': product.presentation,
                'therapeutic_group': product.therapeutic_group,
                'is_controlled': product.is_controlled,
                'sanitary_registration': product.sanitary_registration,
                'laboratory': product.laboratory.name if product.laboratory else None,
                'current_stock': product.current_stock,
                'cost_price': product.cost_price,
                'selling_price': product.calculated_selling_price,
            },
            'in_catalog': True,
        })
    
    # 2. Not in local catalog, try external API
    barcode_service = get_barcode_service()
    api_data = barcode_service.lookup(barcode)
    
    if api_data:
        # Found in external API
        logger.info(
            f"Catalog: barcode '{barcode}' found in external API ({api_data.get('source')})"
        )
        return jsonify({
            'found': True,
            'source': 'external',
            'product': {
                'barcode': api_data.get('barcode'),
                'name': api_data.get('name'),
                'description': api_data.get('description'),
                'brand': api_data.get('brand'),
                'manufacturer': api_data.get('manufacturer'),
                'category': api_data.get('category'),
                'images': api_data.get('images', []),
            },
            'in_catalog': False,
            'suggestion': 'Este producto no está en tu catálogo. ¿Deseas agregarlo?',
        })
    
    # 3. Not found anywhere
    logger.info(f"Catalog: barcode '{barcode}' not found in local or external sources")
    return jsonify({
        'found': False,
        'source': None,
        'error': 'Producto no encontrado',
        'suggestion': 'Puedes agregar este medicamento manualmente al catálogo',
    }), 404


@mobile_api_bp.route('/catalog/products', methods=['POST'])
@token_required
def catalog_add_product(current_user):
    """
    Add a new product to the catalog from mobile app.
    
    Supports adding either:
    - From external API data (after barcode lookup)
    - Manual entry from the app
    
    Input: {
        "company_id": 1,
        "sku": "7501234567890",
        "name": "Paracetamol 500mg",
        "description": "...",
        "active_ingredient": "Paracetamol",
        "presentation": "Tabletas",
        "laboratory_name": "Genomma Lab",  // optional, will create if not exists
        "is_controlled": false,
        "cost_price": 25.50,
        "selling_price": 35.00,
        "min_stock_level": 20
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON'}), 400
    
    company_id = data.get('company_id')
    if not company_id or not current_user.can_access_company(company_id):
        return jsonify({'error': 'Sin acceso a esta empresa'}), 403
    
    # Validate required fields
    sku = (data.get('sku') or '').strip()
    name = (data.get('name') or '').strip()
    
    if not sku or not name:
        return jsonify({'error': 'SKU y nombre son requeridos'}), 400
    
    # Check if product with this SKU already exists
    existing = Product.query.filter_by(
        company_id=company_id,
        sku=sku
    ).first()
    
    if existing:
        return jsonify({
            'error': 'Ya existe un producto con este código de barras',
            'existing_product': {
                'id': existing.id,
                'name': existing.name,
                'sku': existing.sku,
            }
        }), 409
    
    # Handle laboratory (create if doesn't exist)
    laboratory_id = None
    laboratory_name = data.get('laboratory_name', '').strip()
    if laboratory_name:
        from models import Laboratory
        lab = Laboratory.query.filter_by(
            company_id=company_id,
            name=laboratory_name
        ).first()
        
        if not lab:
            lab = Laboratory(
                company_id=company_id,
                name=laboratory_name
            )
            db.session.add(lab)
            db.session.flush()  # Get the ID
        
        laboratory_id = lab.id
    
    # Create product
    product = Product(
        company_id=company_id,
        sku=sku,
        name=name,
        description=data.get('description', ''),
        active_ingredient=data.get('active_ingredient'),
        presentation=data.get('presentation'),
        therapeutic_group=data.get('therapeutic_group'),
        is_controlled=data.get('is_controlled', False),
        sanitary_registration=data.get('sanitary_registration'),
        laboratory_id=laboratory_id,
        cost_price=float(data.get('cost_price', 0)),
        selling_price=float(data.get('selling_price', 0)),
        profit_margin=float(data.get('profit_margin', 0)),
        min_stock_level=int(data.get('min_stock_level', 0)),
        current_stock=0,  # Start with 0 stock
        unit_measure=data.get('unit_measure', 'PZA'),
    )
    
    db.session.add(product)
    db.session.commit()
    
    logger.info(
        f"Catalog: user '{current_user.username}' added product '{name}' "
        f"(SKU: {sku}) to company #{company_id}"
    )
    
    return jsonify({
        'success': True,
        'product': {
            'id': product.id,
            'sku': product.sku,
            'name': product.name,
            'description': product.description,
            'active_ingredient': product.active_ingredient,
            'presentation': product.presentation,
            'is_controlled': product.is_controlled,
            'laboratory': product.laboratory.name if product.laboratory else None,
        },
        'message': 'Producto agregado exitosamente al catálogo'
    }), 201


@mobile_api_bp.route('/catalog/products/<int:product_id>', methods=['PUT'])
@token_required
def catalog_update_product(product_id, current_user):
    """
    Update an existing product in the catalog.
    
    Useful for updating prices, stock levels, or other product information.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Se requiere JSON'}), 400
    
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404
    
    if not current_user.can_access_company(product.company_id):
        return jsonify({'error': 'Sin acceso'}), 403
    
    # Update allowed fields
    if 'name' in data:
        product.name = data['name'].strip()
    if 'description' in data:
        product.description = data['description']
    if 'active_ingredient' in data:
        product.active_ingredient = data['active_ingredient']
    if 'presentation' in data:
        product.presentation = data['presentation']
    if 'therapeutic_group' in data:
        product.therapeutic_group = data['therapeutic_group']
    if 'is_controlled' in data:
        product.is_controlled = data['is_controlled']
    if 'sanitary_registration' in data:
        product.sanitary_registration = data['sanitary_registration']
    if 'cost_price' in data:
        product.cost_price = float(data['cost_price'])
    if 'selling_price' in data:
        product.selling_price = float(data['selling_price'])
    if 'profit_margin' in data:
        product.profit_margin = float(data['profit_margin'])
    if 'min_stock_level' in data:
        product.min_stock_level = int(data['min_stock_level'])
    
    db.session.commit()
    
    logger.info(f"Catalog: user '{current_user.username}' updated product #{product_id}")
    
    return jsonify({
        'success': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
        },
        'message': 'Producto actualizado exitosamente'
    })
