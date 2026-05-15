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


api_bp = Blueprint('api', __name__)

@api_bp.route('/api/companies/<int:company_id>/customers/search')
@login_required
def api_search_customers(company_id):
    """
    Buscar clientes por RFC o nombre para autocompletado.
    Query params: q (texto de búsqueda)
    """
    query_text = request.args.get('q', '').strip()
    
    if not query_text or len(query_text) < 2:
        return jsonify([])
    
    # Buscar por RFC o nombre (case insensitive)
    customers = Customer.query.filter(
        Customer.company_id == company_id,
        db.or_(
            Customer.rfc.ilike(f'{query_text}%'),
            Customer.nombre.ilike(f'%{query_text}%')
        )
    ).limit(10).all()
    
    results = []
    for customer in customers:
        results.append({
            'rfc': customer.rfc,
            'nombre': customer.nombre,
            'codigo_postal': customer.codigo_postal,
            'regimen_fiscal': customer.regimen_fiscal
        })
    
    return jsonify(results)

@api_bp.route('/api/companies/<int:company_id>/customers/<rfc>')
@login_required
def api_get_customer(company_id, rfc):
    """
    Obtener datos completos de un cliente por RFC.
    """
    customer = Customer.query.filter_by(
        company_id=company_id,
        rfc=rfc.upper()
    ).first()
    
    if not customer:
        return jsonify({'error': 'Cliente no encontrado'}), 404
    
    return jsonify({
        'rfc': customer.rfc,
        'nombre': customer.nombre,
        'codigo_postal': customer.codigo_postal,
        'regimen_fiscal': customer.regimen_fiscal
    })

@api_bp.route('/api/companies/<int:company_id>/products/search')
@login_required
def api_search_products(company_id):
    """
    Buscar productos por SKU, nombre o descripción para autocompletado.
    Query params: q (texto de búsqueda)
    """
    query_text = request.args.get('q', '').strip()
    
    if not query_text or len(query_text) < 2:
        return jsonify([])
    
    # Buscar por SKU, nombre o descripción (case insensitive)
    products = Product.query.filter(
        Product.company_id == company_id,
        Product.active == True,
        db.or_(
            Product.sku.ilike(f'{query_text}%'),
            Product.name.ilike(f'%{query_text}%'),
            Product.description.ilike(f'%{query_text}%')
        )
    ).limit(10).all()
    
    results = []
    for product in products:
        results.append({
            'id': product.id,
            'sku': product.sku or '',
            'name': product.name,
            'description': product.description or '',
            'selling_price': float(product.calculated_selling_price),
            'unit_measure': product.unit_measure or 'Servicio'
        })

    return jsonify(results)

@api_bp.route('/api/companies/<int:company_id>/templates/<int:template_id>/items')
@login_required
def api_template_items(company_id, template_id):
    """
    Get items from an invoice template for loading into factura form.
    """
    template = InvoiceTemplate.query.filter_by(
        id=template_id,
        company_id=company_id,
        active=True
    ).first()

    if not template:
        return jsonify({'error': 'Plantilla no encontrada'}), 404

    items = []
    for item in template.items:
        items.append({
            'type': item.item_type,
            'name': item.item_name,
            'quantity': item.quantity,
            'price': item.item_price,
            'product_id': item.product_id,
            'service_id': item.service_id
        })

    return jsonify(items)

@api_bp.route('/api/catalogs/<catalog_type>/search')
@login_required
def api_catalog_search(catalog_type):
    """
    Buscar en catálogos del SAT (Productos, Unidades, etc.)
    """
    from services.catalogs_service import CatalogsService
    
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 50, type=int)
    
    # Limitar a 100 para evitar sobrecarga
    limit = min(limit, 100)
    
    try:
        results = CatalogsService.search_catalog(catalog_type, query, limit)
        return jsonify(results)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Error en búsqueda de catálogo {catalog_type}: {str(e)}')
        return jsonify({'error': 'Error al buscar en catálogo'}), 500

@api_bp.route('/api/catalogs/<catalog_type>/<code>')
@login_required
def api_catalog_get(catalog_type, code):
    """
    Obtener un elemento específico de un catálogo
    """
    from services.catalogs_service import CatalogsService
    
    item = CatalogsService.get_catalog_item(catalog_type, code)
    if not item:
        return jsonify({'error': 'Elemento no encontrado'}), 404
    
    return jsonify(item)

