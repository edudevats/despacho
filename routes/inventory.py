import os
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, limiter, cache, mail, csrf, migrate
from sqlalchemy import func, extract
from datetime import datetime, timedelta, timezone
from utils.timezone_helper import now_mexico, to_mexico_time
from utils.helpers import safe_redirect_target, find_company_invoice_xml_path, parse_invoice_xml_for_db, get_or_create_supplier, update_supplier_stats, PROJECT_ROOT
from utils.decorators import admin_required, inventory_admin_required, require_company_perm
from models import *
from forms import *
from services.sat_service import SATService, SATError
from services.qr_service import QRService

logger = logging.getLogger(__name__)


inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/companies/csf/<int:company_id>', methods=['GET', 'POST'])
@login_required
@require_company_perm('sync')
def download_csf_route(company_id):
    flash('La descarga de CSF (Constancia de Situación Fiscal) no está disponible actualmente.', 'warning')
    return redirect(url_for('companies.companies'))

@inventory_bp.route('/invoices/<uuid>/download/<file_type>')
@login_required
def download_invoice_file(uuid, file_type):
    """
    Descarga el archivo XML o genera y descarga PDF de una factura.
    
    Args:
        uuid: UUID de la factura
        file_type: 'xml' o 'pdf'
    """
    invoice = Invoice.query.filter_by(uuid=uuid).first_or_404()

    # IDOR protection: only allow download if the user has the 'invoices'
    # permission on the company that owns this invoice. Global admins pass.
    from flask import abort
    if not current_user.has_company_perm(invoice.company_id, 'invoices'):
        abort(403)

    if file_type == 'xml':
        # Servir XML almacenado
        return Response(
            invoice.xml_content,
            mimetype='application/xml',
            headers={'Content-Disposition': f'attachment; filename={uuid}.xml'}
        )
    elif file_type == 'pdf':
        # Generar PDF bajo demanda desde el XML usando satcfdi
        try:
            # Genera PDF usando satcfdi (genera PDFs profesionales de alta calidad)
            pdf_bytes = SATService.generate_pdf(invoice.xml_content)
            
            return Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment; filename={uuid}.pdf'}
            )
        except Exception as e:
            logger.error(f'Error generando PDF para factura {uuid}: {str(e)}')
            flash('Error al generar el PDF. Por favor intente nuevamente.', 'error')
            # Validate referrer to prevent open-redirect.
            return redirect(safe_redirect_target(request.referrer, url_for('main.index')))
    else:
        from flask import abort
        abort(400)

@inventory_bp.route('/logos/<filename>')
def serve_logo(filename):
    """Servir archivos de logos de empresas"""
    from flask import send_from_directory
    logos_dir = os.path.join(os.path.dirname(__file__), 'logos')
    return send_from_directory(logos_dir, filename)

@inventory_bp.route('/movements')
@login_required
def movements():
    """Redirect to unified search/movements page"""
    return redirect(url_for('inventory.search_advanced'))

@inventory_bp.route('/sync')
@login_required
def sync_list():
    """Show list of companies to sync"""
    companies_list = current_user.accessible_companies_with_perm('sync')
    return render_template('sync_list.html', companies=companies_list)

@inventory_bp.route('/search/advanced')
@login_required
def search_advanced():
    """Show list of companies for advanced search"""
    companies_list = current_user.accessible_companies_with_perm('invoices')
    return render_template('search_list.html', companies=companies_list)

@inventory_bp.route('/taxes')
@login_required
def taxes_list():
    """Show list of companies for tax calculations"""
    companies_list = current_user.accessible_companies_with_perm('taxes')
    return render_template('taxes_list.html', companies=companies_list)

@inventory_bp.route('/companies/<int:company_id>/suppliers')
@login_required
@require_company_perm('inventory', 'inventory_admin')
def suppliers(company_id):
    """Lista de proveedores con estadísticas"""
    company = Company.query.get_or_404(company_id)
    
    # Filtros
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'total')  # total, name, count
    
    query = Supplier.query.filter_by(company_id=company_id, active=True)
    
    if search:
        query = query.filter(
            db.or_(
                Supplier.business_name.ilike(f'%{search}%'),
                Supplier.rfc.ilike(f'%{search}%')
            )
        )
    
    if sort_by == 'total':
        query = query.order_by(Supplier.total_invoiced.desc())
    elif sort_by == 'name':
        query = query.order_by(Supplier.business_name)
    elif sort_by == 'count':
        query = query.order_by(Supplier.invoice_count.desc())
    
    suppliers_list = query.all()
    
    # Estadísticas generales
    total_suppliers = len(suppliers_list)
    total_spent = sum(s.total_invoiced for s in suppliers_list)
    
    return render_template('suppliers/list.html',
        company=company,
        suppliers=suppliers_list,
        total_suppliers=total_suppliers,
        total_spent=total_spent,
        search=search,
        sort_by=sort_by
    )

@inventory_bp.route('/companies/<int:company_id>/suppliers/<int:supplier_id>')
@login_required
@require_company_perm('inventory', 'inventory_admin')
def supplier_detail(company_id, supplier_id):
    """Detalle de un proveedor específico con sus facturas"""
    company = Company.query.get_or_404(company_id)
    supplier = Supplier.query.get_or_404(supplier_id)
    
    # Verificar que el proveedor pertenece a esta empresa
    if supplier.company_id != company_id:
        flash('Proveedor no encontrado', 'error')
        return redirect(url_for('inventory.suppliers', company_id=company_id))
    
    # Facturas del proveedor
    invoices = Invoice.query.filter_by(
        company_id=company_id,
        supplier_id=supplier_id
    ).order_by(Invoice.date.desc()).all()
    
    # Tendencia mensual
    monthly_data = db.session.query(
        extract('year', Invoice.date).label('year'),
        extract('month', Invoice.date).label('month'),
        func.sum(Invoice.total).label('total'),
        func.count(Invoice.id).label('count')
    ).filter(
        Invoice.company_id == company_id,
        Invoice.supplier_id == supplier_id
    ).group_by('year', 'month').order_by('year', 'month').all()
    
    return render_template('suppliers/detail.html',
        company=company,
        supplier=supplier,
        invoices=invoices,
        monthly_data=monthly_data
    )

@inventory_bp.route('/companies/<int:company_id>/categories')
@login_required
@require_company_perm('inventory', 'inventory_admin')
def categories(company_id):
    """Gestión de categorías"""
    company = Company.query.get_or_404(company_id)
    
    income_categories = Category.query.filter_by(
        company_id=company_id,
        type='INCOME',
        active=True
    ).all()
    
    expense_categories = Category.query.filter_by(
        company_id=company_id,
        type='EXPENSE',
        active=True
    ).all()
    
    return render_template('categories/list.html',
        company=company,
        income_categories=income_categories,
        expense_categories=expense_categories
    )

@inventory_bp.route('/companies/<int:company_id>/ppd')
@login_required
@require_company_perm('ppd', 'invoices')
def ppd_list(company_id):
    """Gestión de facturas PPD (Pago en Parcialidades o Diferido)"""
    company = Company.query.get_or_404(company_id)
    
    # Facturas PPD pendientes (no acreditadas)
    pending_invoices = Invoice.query.filter(
        Invoice.company_id == company_id,
        Invoice.metodo_pago == 'PPD',
        Invoice.ppd_acreditado == False
    ).order_by(Invoice.date.asc()).all()
    
    # Facturas PPD ya acreditadas
    accredited_invoices = Invoice.query.filter(
        Invoice.company_id == company_id,
        Invoice.metodo_pago == 'PPD',
        Invoice.ppd_acreditado == True
    ).order_by(Invoice.ppd_anio_acreditado.desc(), Invoice.ppd_mes_acreditado.desc()).all()
    
    # Get selected invoice from query param for highlighting
    selected_invoice_id = request.args.get('invoice_id', type=int)
    
    from datetime import datetime
    return render_template('ppd/list.html',
        company=company,
        pending_invoices=pending_invoices,
        accredited_invoices=accredited_invoices,
        selected_invoice_id=selected_invoice_id,
        current_year=now_mexico().year
    )

@inventory_bp.route('/companies/<int:company_id>/ppd/<int:invoice_id>/acreditar', methods=['POST'])
@login_required
@require_company_perm('ppd', 'invoices')
def ppd_acreditar(company_id, invoice_id):
    """Acreditar una factura PPD a un mes específico"""
    company = Company.query.get_or_404(company_id)
    invoice = Invoice.query.get_or_404(invoice_id)
    
    if invoice.company_id != company_id:
        flash('Factura no encontrada', 'error')
        return redirect(url_for('inventory.ppd_list', company_id=company_id))
        
    if invoice.metodo_pago != 'PPD':
        flash('Solo se pueden acreditar facturas PPD', 'error')
        return redirect(url_for('inventory.ppd_list', company_id=company_id))
        
    mes = request.form.get('mes_acreditado', type=int)
    anio = request.form.get('anio_acreditado', type=int)
    
    if not mes or not anio:
        flash('Debe seleccionar mes y año', 'error')
        return redirect(url_for('inventory.ppd_list', company_id=company_id))
        
    try:
        from datetime import datetime
        
        # 1. Update Invoice status
        invoice.ppd_acreditado = True
        invoice.ppd_mes_acreditado = mes
        invoice.ppd_anio_acreditado = anio
        invoice.ppd_fecha_acreditacion = now_mexico()
        
        # 2. Create Movement
        # Set date to the 1st of the accredited month/year so it appears in that month's reports
        movement_date = datetime(anio, mes, 1)
        
        # Determine type (Ingreso/Egreso)
        is_emitted = (invoice.issuer_rfc == company.rfc)
        mov_type = 'INCOME' if is_emitted else 'EXPENSE'
        
        description = f"Factura PPD {invoice.uuid[:8]}... (Acreditada en {mes}/{anio})"
        
        new_mov = Movement(
            invoice=invoice,
            company_id=company.id,
            amount=invoice.total,
            type=mov_type,
            description=description,
            date=movement_date,
            source='manual_ppd'
        )
        db.session.add(new_mov)
        
        db.session.commit()
        flash('Factura acreditada correctamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al acreditar factura: {str(e)}', 'error')
        
    return redirect(url_for('inventory.ppd_list', company_id=company_id))

@inventory_bp.route('/companies/<int:company_id>/ppd/<int:invoice_id>/desacreditar', methods=['POST'])
@login_required
@require_company_perm('ppd', 'invoices')
def ppd_desacreditar(company_id, invoice_id):
    """Remover acreditación de una factura PPD"""
    company = Company.query.get_or_404(company_id)
    invoice = Invoice.query.get_or_404(invoice_id)
    
    if invoice.company_id != company_id:
        flash('Factura no encontrada', 'error')
        return redirect(url_for('inventory.ppd_list', company_id=company_id))
        
    try:
        # 1. Delete associated Movement
        if invoice.movement:
            db.session.delete(invoice.movement)
        else:
            # Fallback if relationship is not set but movement exists (search manually)
            Movement.query.filter_by(invoice_id=invoice.id).delete()
        
        # 2. Reset Invoice status
        invoice.ppd_acreditado = False
        invoice.ppd_mes_acreditado = None
        invoice.ppd_anio_acreditado = None
        invoice.ppd_fecha_acreditacion = None
        
        db.session.commit()
        flash('Acreditación removida correctamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al remover acreditación: {str(e)}', 'error')
        
    return redirect(url_for('inventory.ppd_list', company_id=company_id))

@inventory_bp.route('/inventory')
@login_required
def inventory_companies_list():
    """Show list of companies for inventory management"""
    companies_list = current_user.accessible_companies_with_perm('inventory', 'inventory_admin')
    return render_template('inventory_list_companies.html', companies=companies_list)

def _ensure_default_product_categories(company_id):
    """Crear categorías por defecto si no existen para esta empresa"""
    defaults = [
        {'name': 'Medicamento', 'description': 'Medicamentos y fármacos',
         'requires_cofepris': True, 'requires_batch_tracking': True},
        {'name': 'Insumo', 'description': 'Insumos médicos y materiales',
         'requires_cofepris': False, 'requires_batch_tracking': False},
    ]
    created = False
    for d in defaults:
        existing = ProductCategory.query.filter_by(company_id=company_id, name=d['name']).first()
        if not existing:
            cat = ProductCategory(company_id=company_id, **d)
            db.session.add(cat)
            created = True
    if created:
        db.session.commit()

@inventory_bp.route('/companies/<int:company_id>/inventory')
@login_required
def inventory_list(company_id):
    """Listado de productos e inventario con tabs"""
    company = Company.query.get_or_404(company_id)

    # Asegurar categorías por defecto
    _ensure_default_product_categories(company_id)

    # Obtener el tab activo desde URL params
    active_tab = request.args.get('tab', 'products')

    # Cargar categorías de producto
    product_categories = ProductCategory.query.filter_by(company_id=company_id, active=True).order_by(ProductCategory.name).all()

    # Cargar productos con filtro opcional por categoría
    products_query = Product.query.filter_by(company_id=company_id, active=True)
    category_filter = request.args.get('category_id', type=int)
    if category_filter:
        products_query = products_query.filter(Product.category_id == category_filter)
    products = products_query.order_by(Product.name).all()
    total_inventory_value = sum(p.current_stock * p.cost_price for p in products)
    total_items = sum(p.current_stock for p in products)

    # Cargar laboratorios
    laboratories = Laboratory.query.filter_by(company_id=company_id).order_by(Laboratory.name).all()

    # Cargar proveedores
    suppliers = Supplier.query.filter_by(company_id=company_id, active=True).order_by(Supplier.business_name).all()

    # Cargar ordenes de compra
    purchase_orders = PurchaseOrder.query.filter_by(company_id=company_id).order_by(PurchaseOrder.created_at.desc()).all()

    # Cargar ordenes de salida
    exit_orders = ExitOrder.query.filter_by(company_id=company_id).order_by(ExitOrder.created_at.desc()).all()

    # Cargar servicios
    services = Service.query.filter_by(company_id=company_id).order_by(Service.name).all()

    # Cargar plantillas de factura
    invoice_templates = InvoiceTemplate.query.filter_by(company_id=company_id).order_by(InvoiceTemplate.name).all()

    # Alertas de caducidad - productos que vencen en los proximos 90 dias
    today = now_mexico().date()
    expiring_soon_date = today + timedelta(days=90)
    expiring_batches = db.session.query(ProductBatch, Product).join(Product).filter(
        Product.company_id == company_id,
        ProductBatch.current_stock > 0,
        ProductBatch.expiration_date != None,
        ProductBatch.expiration_date <= expiring_soon_date
    ).order_by(ProductBatch.expiration_date.asc()).all()

    # Separar por urgencia
    expired_batches = [(b, p) for b, p in expiring_batches if b.expiration_date < today]
    critical_batches = [(b, p) for b, p in expiring_batches if today <= b.expiration_date <= today + timedelta(days=30)]
    warning_batches = [(b, p) for b, p in expiring_batches if today + timedelta(days=30) < b.expiration_date <= expiring_soon_date]

    # Solicitudes de inventario
    pending_requests_count = InventoryRequest.query.filter_by(
        company_id=company_id, status='PENDING'
    ).count()

    if current_user.is_admin:
        inventory_requests = InventoryRequest.query.filter_by(
            company_id=company_id
        ).order_by(InventoryRequest.created_at.desc()).limit(50).all()
    else:
        inventory_requests = InventoryRequest.query.filter_by(
            company_id=company_id, created_by_id=current_user.id
        ).order_by(InventoryRequest.created_at.desc()).limit(50).all()

    # Permisos del usuario para la empresa
    perms = current_user.get_company_permissions(company_id) if not current_user.is_admin else {}

    return render_template('inventory/list.html',
                           company=company,
                           products=products,
                           total_inventory_value=total_inventory_value,
                           total_items=total_items,
                           laboratories=laboratories,
                           suppliers=suppliers,
                           purchase_orders=purchase_orders,
                           exit_orders=exit_orders,
                           services=services,
                           invoice_templates=invoice_templates,
                           active_tab=active_tab,
                           expired_batches=expired_batches,
                           critical_batches=critical_batches,
                           warning_batches=warning_batches,
                           today=today,
                           pending_requests_count=pending_requests_count,
                           inventory_requests=inventory_requests,
                           perms=perms,
                           product_categories=product_categories,
                           category_filter=category_filter)

@inventory_bp.route('/companies/<int:company_id>/inventory/add', methods=['GET', 'POST'])
@inventory_admin_required
def add_product(company_id):
    """Agregar nuevo producto"""
    company = Company.query.get_or_404(company_id)
    form = ProductForm()

    # Cargar opciones de laboratorios, proveedores y categorías
    laboratories = Laboratory.query.filter_by(company_id=company_id, active=True).order_by(Laboratory.name).all()
    suppliers = Supplier.query.filter_by(company_id=company_id, active=True).order_by(Supplier.business_name).all()
    categories = ProductCategory.query.filter_by(company_id=company_id, active=True).order_by(ProductCategory.name).all()

    form.laboratory_id.choices = [(0, '-- Sin laboratorio --')] + [(l.id, l.name) for l in laboratories]
    form.preferred_supplier_id.choices = [(0, '-- Sin proveedor --')] + [(s.id, f"{s.business_name} ({s.rfc})") for s in suppliers]
    form.category_id.choices = [(0, '-- Sin categoría --')] + [(c.id, c.name) for c in categories]

    if form.validate_on_submit():
        new_product = Product(
            company_id=company_id,
            name=form.name.data,
            sku=form.sku.data,
            description=form.description.data,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            cost_price=form.cost_price.data or 0,
            selling_price=form.selling_price.data or 0,
            profit_margin=form.profit_margin.data or 0,
            laboratory_id=form.laboratory_id.data if form.laboratory_id.data != 0 else None,
            preferred_supplier_id=form.preferred_supplier_id.data if form.preferred_supplier_id.data != 0 else None,
            current_stock=0,
            min_stock_level=form.min_stock_level.data or 0,
            # Empaque
            packaging_type=form.packaging_type.data or None,
            units_per_package=form.units_per_package.data or 1,
            sell_by=form.sell_by.data,
            # COFEPRIS Fields
            is_controlled=form.is_controlled.data,
            active_ingredient=form.active_ingredient.data,
            presentation=form.presentation.data,
            therapeutic_group=form.therapeutic_group.data,
            unit_measure=form.unit_measure.data
        )

        db.session.add(new_product)
        db.session.commit()
        flash(f'Producto "{new_product.name}" agregado correctamente.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id))

    return render_template('inventory/add.html', company=company, form=form)

@inventory_bp.route('/companies/<int:company_id>/inventory/<int:product_id>/edit', methods=['GET', 'POST'])
@inventory_admin_required
def edit_product(company_id, product_id):
    """Editar producto"""
    company = Company.query.get_or_404(company_id)
    product = Product.query.get_or_404(product_id)

    if product.company_id != company_id:
        flash('Producto no encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id))

    form = ProductForm(obj=product)

    # Cargar opciones de laboratorios, proveedores y categorías
    laboratories = Laboratory.query.filter_by(company_id=company_id, active=True).order_by(Laboratory.name).all()
    suppliers = Supplier.query.filter_by(company_id=company_id, active=True).order_by(Supplier.business_name).all()
    categories = ProductCategory.query.filter_by(company_id=company_id, active=True).order_by(ProductCategory.name).all()

    form.laboratory_id.choices = [(0, '-- Sin laboratorio --')] + [(l.id, l.name) for l in laboratories]
    form.preferred_supplier_id.choices = [(0, '-- Sin proveedor --')] + [(s.id, f"{s.business_name} ({s.rfc})") for s in suppliers]
    form.category_id.choices = [(0, '-- Sin categoría --')] + [(c.id, c.name) for c in categories]

    if form.validate_on_submit():
        product.name = form.name.data
        product.sku = form.sku.data
        product.description = form.description.data
        product.category_id = form.category_id.data if form.category_id.data != 0 else None
        product.cost_price = form.cost_price.data or 0
        product.selling_price = form.selling_price.data or 0
        product.profit_margin = form.profit_margin.data or 0
        product.laboratory_id = form.laboratory_id.data if form.laboratory_id.data != 0 else None
        product.preferred_supplier_id = form.preferred_supplier_id.data if form.preferred_supplier_id.data != 0 else None
        product.min_stock_level = form.min_stock_level.data or 0
        # Empaque
        product.packaging_type = form.packaging_type.data or None
        product.units_per_package = form.units_per_package.data or 1
        product.sell_by = form.sell_by.data
        # COFEPRIS
        product.sanitary_registration = form.sanitary_registration.data
        product.is_controlled = form.is_controlled.data
        product.active_ingredient = form.active_ingredient.data
        product.presentation = form.presentation.data
        product.therapeutic_group = form.therapeutic_group.data
        product.unit_measure = form.unit_measure.data

        db.session.commit()
        flash(f'Producto "{product.name}" actualizado.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id))

    return render_template('inventory/edit.html', company=company, product=product, form=form)

@inventory_bp.route('/companies/<int:company_id>/inventory/<int:product_id>/adjust', methods=['GET', 'POST'])
@inventory_admin_required
def adjust_stock(company_id, product_id):
    """Corrección manual de stock - solo para administradores"""
    company = Company.query.get_or_404(company_id)
    product = Product.query.get_or_404(product_id)

    if product.company_id != company_id:
        flash('Producto no encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id))

    requires_batches = bool(product.category and product.category.requires_batch_tracking)
    today = now_mexico().date()

    active_batches = ProductBatch.query.filter(
        ProductBatch.product_id == product.id,
        ProductBatch.current_stock > 0,
        ProductBatch.is_active == True
    ).order_by(ProductBatch.expiration_date.asc()).all()

    # All batches (for expiration date editing section)
    all_batches = ProductBatch.query.filter(
        ProductBatch.product_id == product.id,
    ).order_by(ProductBatch.expiration_date.asc()).all()

    if request.method == 'POST':
        adjustment_type = request.form.get('type', 'IN')
        quantity = request.form.get('quantity', type=int)
        notes = request.form.get('notes', '').strip()

        def render_form():
            return render_template(
                'inventory/adjust.html',
                company=company,
                product=product,
                active_batches=active_batches,
                all_batches=all_batches,
                requires_batches=requires_batches,
                today=today,
            )

        if not notes:
            flash('Debe escribir una nota explicando el motivo de la corrección.', 'error')
            return render_form()

        if not quantity or quantity <= 0:
            flash('La cantidad debe ser mayor a cero.', 'error')
            return render_form()

        previous_stock = product.current_stock
        batch = None

        if adjustment_type == 'IN':
            if requires_batches:
                batch_number = request.form.get('batch_number', '').strip()
                expiration_str = request.form.get('expiration_date', '').strip()

                if not batch_number:
                    flash('Debe ingresar el número de lote.', 'error')
                    return render_form()
                if not expiration_str:
                    flash('Debe ingresar la fecha de caducidad.', 'error')
                    return render_form()
                try:
                    expiration_date = datetime.strptime(expiration_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Fecha de caducidad inválida.', 'error')
                    return render_form()

                existing = ProductBatch.query.filter_by(
                    product_id=product.id,
                    batch_number=batch_number,
                    expiration_date=expiration_date
                ).first()

                if existing:
                    existing.current_stock += quantity
                    existing.initial_stock = (existing.initial_stock or 0) + quantity
                    existing.is_active = True
                    batch = existing
                else:
                    batch = ProductBatch(
                        product_id=product.id,
                        batch_number=batch_number,
                        expiration_date=expiration_date,
                        initial_stock=quantity,
                        current_stock=quantity,
                        acquisition_date=now_mexico().date(),
                        is_active=True,
                    )
                    db.session.add(batch)
                    db.session.flush()

            new_stock = previous_stock + quantity
        else:
            if requires_batches:
                batch_id = request.form.get('batch_id', type=int)
                if not batch_id:
                    flash('Debe seleccionar el lote del que se descontará.', 'error')
                    return render_form()

                batch = ProductBatch.query.filter_by(id=batch_id, product_id=product.id).first()
                if not batch:
                    flash('Lote no encontrado.', 'error')
                    return render_form()
                if quantity > batch.current_stock:
                    flash(f'El lote seleccionado solo tiene {batch.current_stock} unidades.', 'error')
                    return render_form()

                batch.current_stock -= quantity
                if batch.current_stock <= 0:
                    batch.is_active = False

            new_stock = max(0, previous_stock - quantity)

        transaction = InventoryTransaction(
            product_id=product.id,
            batch_id=batch.id if batch else None,
            type='ADJUSTMENT',
            quantity=quantity,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reference=f'Corrección Admin - {current_user.username}',
            notes=f'[CORRECCIÓN ADMIN: {current_user.username}] {notes}',
            created_by_id=current_user.id
        )
        db.session.add(transaction)
        product.current_stock = new_stock
        db.session.commit()

        logger.info(f"Admin stock adjustment by {current_user.username}: product {product_id}, {previous_stock} -> {new_stock}, reason: {notes}")
        flash(f'Corrección registrada. Stock: {previous_stock} → {new_stock}', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id))

    return render_template(
        'inventory/adjust.html',
        company=company,
        product=product,
        active_batches=active_batches,
        all_batches=all_batches,
        requires_batches=requires_batches,
        today=today,
    )

@inventory_bp.route('/companies/<int:company_id>/inventory/<int:product_id>/batch/<int:batch_id>/update-expiration', methods=['POST'])
@inventory_admin_required
def update_batch_expiration(company_id, product_id, batch_id):
    """Actualizar fecha de caducidad de un lote - solo administradores"""
    company = Company.query.get_or_404(company_id)
    product = Product.query.get_or_404(product_id)

    if product.company_id != company_id:
        flash('Producto no encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id))

    batch = ProductBatch.query.get_or_404(batch_id)
    if batch.product_id != product.id:
        flash('Lote no encontrado para este producto.', 'error')
        return redirect(url_for('inventory.adjust_stock', company_id=company_id, product_id=product_id))

    new_expiration_str = request.form.get('new_expiration_date', '').strip()
    reason = request.form.get('reason', '').strip()

    if not new_expiration_str:
        flash('Debe ingresar la nueva fecha de caducidad.', 'error')
        return redirect(url_for('inventory.adjust_stock', company_id=company_id, product_id=product_id))

    if not reason or len(reason) < 5:
        flash('Debe escribir el motivo del cambio (mínimo 5 caracteres).', 'error')
        return redirect(url_for('inventory.adjust_stock', company_id=company_id, product_id=product_id))

    try:
        new_expiration = datetime.strptime(new_expiration_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Fecha de caducidad inválida.', 'error')
        return redirect(url_for('inventory.adjust_stock', company_id=company_id, product_id=product_id))

    old_expiration = batch.expiration_date
    if old_expiration == new_expiration:
        flash('La fecha de caducidad es la misma, no se realizaron cambios.', 'info')
        return redirect(url_for('inventory.adjust_stock', company_id=company_id, product_id=product_id))

    # Update the expiration date
    batch.expiration_date = new_expiration

    # Log the change as an ADJUSTMENT transaction for audit trail
    transaction = InventoryTransaction(
        product_id=product.id,
        batch_id=batch.id,
        type='ADJUSTMENT',
        quantity=0,
        previous_stock=product.current_stock,
        new_stock=product.current_stock,
        reference=f'Cambio fecha caducidad - {current_user.username}',
        notes=f'[CAMBIO CADUCIDAD: {current_user.username}] Lote {batch.batch_number}: {old_expiration.strftime("%d/%m/%Y")} → {new_expiration.strftime("%d/%m/%Y")} | Motivo: {reason}',
        created_by_id=current_user.id
    )
    db.session.add(transaction)
    db.session.commit()

    logger.info(f"Admin batch expiration update by {current_user.username}: batch {batch.batch_number} (product {product_id}), {old_expiration} -> {new_expiration}, reason: {reason}")
    flash(f'Fecha de caducidad del lote {batch.batch_number} actualizada: {old_expiration.strftime("%d/%m/%Y")} → {new_expiration.strftime("%d/%m/%Y")}', 'success')
    return redirect(url_for('inventory.adjust_stock', company_id=company_id, product_id=product_id))

@inventory_bp.route('/companies/<int:company_id>/inventory/<int:product_id>/history')
@inventory_admin_required
def product_history(company_id, product_id):
    """Historial de movimientos de un producto"""
    company = Company.query.get_or_404(company_id)
    product = Product.query.get_or_404(product_id)

    if product.company_id != company_id:
        return redirect(url_for('inventory.inventory_list', company_id=company_id))

    transactions = InventoryTransaction.query.filter_by(
        product_id=product_id
    ).order_by(InventoryTransaction.date.desc()).all()

    return render_template('inventory/history.html', company=company, product=product, transactions=transactions)

@inventory_bp.route('/companies/<int:company_id>/inventory/movements')
@inventory_admin_required
def inventory_movements(company_id):
    """Registro completo de movimientos de inventario de la empresa"""
    company = Company.query.get_or_404(company_id)

    # Filtros opcionales por query string
    type_filter = request.args.get('type', '')        # IN, OUT, ADJUSTMENT
    product_filter = request.args.get('product_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = (
        InventoryTransaction.query
        .join(Product, InventoryTransaction.product_id == Product.id)
        .filter(Product.company_id == company_id)
        .order_by(InventoryTransaction.date.desc())
    )

    if type_filter:
        query = query.filter(InventoryTransaction.type == type_filter)
    if product_filter:
        query = query.filter(InventoryTransaction.product_id == product_filter)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(InventoryTransaction.date >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            query = query.filter(InventoryTransaction.date <= dt_to)
        except ValueError:
            pass

    transactions = query.limit(500).all()
    products = Product.query.filter_by(company_id=company_id, active=True).order_by(Product.name).all()

    return render_template('inventory/movements.html',
                           company=company,
                           transactions=transactions,
                           products=products,
                           type_filter=type_filter,
                           product_filter=product_filter,
                           date_from=date_from,
                           date_to=date_to)

@inventory_bp.route('/companies/<int:company_id>/inventory/analytics')
@inventory_admin_required
def inventory_analytics(company_id):
    """Análisis de inventario: ABC/Pareto, rotación y antigüedad de lotes."""
    company = Company.query.get_or_404(company_id)

    # Ventana configurable por query string (30 / 60 / 90 / 180 días)
    try:
        window_days = int(request.args.get('window', 90))
    except (TypeError, ValueError):
        window_days = 90
    if window_days not in (30, 60, 90, 180, 365):
        window_days = 90

    today = now_mexico().date()
    window_start = datetime.combine(today - timedelta(days=window_days), datetime.min.time())

    # ----- Datos base -----
    products = (Product.query
                .filter_by(company_id=company_id, active=True)
                .order_by(Product.name)
                .all())

    # Salidas agregadas por producto en la ventana
    out_by_product = dict(
        db.session.query(
            InventoryTransaction.product_id,
            func.coalesce(func.sum(InventoryTransaction.quantity), 0)
        )
        .join(Product, InventoryTransaction.product_id == Product.id)
        .filter(
            Product.company_id == company_id,
            InventoryTransaction.type == 'OUT',
            InventoryTransaction.date >= window_start
        )
        .group_by(InventoryTransaction.product_id)
        .all()
    )

    # Última fecha de OUT por producto (para detectar productos muertos)
    last_out_by_product = dict(
        db.session.query(
            InventoryTransaction.product_id,
            func.max(InventoryTransaction.date)
        )
        .join(Product, InventoryTransaction.product_id == Product.id)
        .filter(
            Product.company_id == company_id,
            InventoryTransaction.type == 'OUT'
        )
        .group_by(InventoryTransaction.product_id)
        .all()
    )

    # ----- ABC / Pareto -----
    abc_rows = []
    for p in products:
        value = (p.current_stock or 0) * (p.cost_price or 0.0)
        abc_rows.append({
            'product': p,
            'stock': p.current_stock or 0,
            'cost': p.cost_price or 0.0,
            'value': value,
        })
    abc_rows.sort(key=lambda r: r['value'], reverse=True)
    total_value = sum(r['value'] for r in abc_rows) or 0.0
    cum = 0.0
    for r in abc_rows:
        cum += r['value']
        r['cumulative'] = cum
        r['cum_pct'] = (cum / total_value * 100) if total_value > 0 else 0
        r['value_pct'] = (r['value'] / total_value * 100) if total_value > 0 else 0
        if r['cum_pct'] <= 80:
            r['abc_class'] = 'A'
        elif r['cum_pct'] <= 95:
            r['abc_class'] = 'B'
        else:
            r['abc_class'] = 'C'

    abc_summary = {
        'A': {'count': sum(1 for r in abc_rows if r['abc_class'] == 'A'),
              'value': sum(r['value'] for r in abc_rows if r['abc_class'] == 'A')},
        'B': {'count': sum(1 for r in abc_rows if r['abc_class'] == 'B'),
              'value': sum(r['value'] for r in abc_rows if r['abc_class'] == 'B')},
        'C': {'count': sum(1 for r in abc_rows if r['abc_class'] == 'C'),
              'value': sum(r['value'] for r in abc_rows if r['abc_class'] == 'C')},
        'total_value': total_value,
        'total_count': len(abc_rows),
    }

    # ----- Rotación -----
    # Clasificación basada en cobertura: si las salidas en la ventana cubren >= 1 stock actual → rápido
    rotation_rows = []
    for p in products:
        qty_out = int(out_by_product.get(p.id, 0) or 0)
        stock = p.current_stock or 0
        last_out = last_out_by_product.get(p.id)
        days_since_last = None
        if last_out:
            days_since_last = (now_mexico().replace(tzinfo=None) - last_out).days
        # Tasa mensual estimada
        monthly_rate = (qty_out / window_days * 30.0) if window_days > 0 else 0
        # Cobertura: cuántas ventanas-de-tamaño-window puede cubrir el stock
        coverage_ratio = (stock / qty_out) if qty_out > 0 else None
        if qty_out == 0 and stock > 0:
            rclass = 'dead'
        elif qty_out >= stock and stock > 0:
            rclass = 'fast'
        elif qty_out > 0:
            rclass = 'slow'
        else:
            rclass = 'empty'  # ni stock ni movimiento
        rotation_rows.append({
            'product': p,
            'stock': stock,
            'qty_out': qty_out,
            'monthly_rate': monthly_rate,
            'coverage_ratio': coverage_ratio,
            'last_out': last_out,
            'days_since_last': days_since_last,
            'class': rclass,
            'value_at_risk': stock * (p.cost_price or 0.0) if rclass == 'dead' else 0,
        })

    rotation_summary = {
        'fast':  sum(1 for r in rotation_rows if r['class'] == 'fast'),
        'slow':  sum(1 for r in rotation_rows if r['class'] == 'slow'),
        'dead':  sum(1 for r in rotation_rows if r['class'] == 'dead'),
        'empty': sum(1 for r in rotation_rows if r['class'] == 'empty'),
        'value_at_risk': sum(r['value_at_risk'] for r in rotation_rows),
    }
    # Mostrar ordenados: dead primero (mayor valor en riesgo), luego slow, luego fast
    rotation_rows.sort(key=lambda r: (
        {'dead': 0, 'slow': 1, 'fast': 2, 'empty': 3}[r['class']],
        -r['value_at_risk'],
        -r['qty_out']
    ))

    # ----- Antigüedad de lotes -----
    active_batches = (
        db.session.query(ProductBatch, Product)
        .join(Product, ProductBatch.product_id == Product.id)
        .filter(
            Product.company_id == company_id,
            ProductBatch.current_stock > 0
        )
        .order_by(ProductBatch.acquisition_date.asc())
        .all()
    )
    aging_rows = []
    for batch, p in active_batches:
        acq = batch.acquisition_date
        if acq is None:
            continue
        if hasattr(acq, 'date'):
            acq_date = acq.date()
        else:
            acq_date = acq
        days_in_stock = (today - acq_date).days
        days_to_expire = (batch.expiration_date - today).days if batch.expiration_date else None
        if days_in_stock >= 365:
            bucket = 'over_year'
        elif days_in_stock >= 180:
            bucket = '180_365'
        elif days_in_stock >= 90:
            bucket = '90_180'
        elif days_in_stock >= 30:
            bucket = '30_90'
        else:
            bucket = 'fresh'
        aging_rows.append({
            'batch': batch,
            'product': p,
            'acq_date': acq_date,
            'days_in_stock': days_in_stock,
            'days_to_expire': days_to_expire,
            'bucket': bucket,
            'value': (batch.current_stock or 0) * (p.cost_price or 0.0),
        })
    aging_rows.sort(key=lambda r: r['days_in_stock'], reverse=True)
    aging_summary = {
        'over_year': sum(1 for r in aging_rows if r['bucket'] == 'over_year'),
        '180_365':   sum(1 for r in aging_rows if r['bucket'] == '180_365'),
        '90_180':    sum(1 for r in aging_rows if r['bucket'] == '90_180'),
        '30_90':     sum(1 for r in aging_rows if r['bucket'] == '30_90'),
        'fresh':     sum(1 for r in aging_rows if r['bucket'] == 'fresh'),
        'old_value': sum(r['value'] for r in aging_rows if r['bucket'] in ('over_year', '180_365')),
    }

    return render_template(
        'inventory/analytics.html',
        company=company,
        window_days=window_days,
        abc_rows=abc_rows,
        abc_summary=abc_summary,
        rotation_rows=rotation_rows,
        rotation_summary=rotation_summary,
        aging_rows=aging_rows,
        aging_summary=aging_summary,
    )

@inventory_bp.route('/companies/<int:company_id>/inventory/reorder')
@inventory_admin_required
def inventory_reorder(company_id):
    """Sugerencia de reorden basada en consumo histórico × lead time."""
    company = Company.query.get_or_404(company_id)

    # Parámetros configurables
    try:
        lead_days = int(request.args.get('lead', 7))
    except (TypeError, ValueError):
        lead_days = 7
    if lead_days < 1: lead_days = 1
    if lead_days > 90: lead_days = 90

    try:
        window_days = int(request.args.get('window', 90))
    except (TypeError, ValueError):
        window_days = 90
    if window_days not in (30, 60, 90, 180): window_days = 90

    try:
        target_days = int(request.args.get('target', 30))  # Cuántos días de stock objetivo después de reponer
    except (TypeError, ValueError):
        target_days = 30
    if target_days < 7: target_days = 7
    if target_days > 180: target_days = 180

    today = now_mexico().date()
    window_start = datetime.combine(today - timedelta(days=window_days), datetime.min.time())

    products = (Product.query
                .filter_by(company_id=company_id, active=True)
                .order_by(Product.name)
                .all())

    out_by_product = dict(
        db.session.query(
            InventoryTransaction.product_id,
            func.coalesce(func.sum(InventoryTransaction.quantity), 0)
        )
        .join(Product, InventoryTransaction.product_id == Product.id)
        .filter(
            Product.company_id == company_id,
            InventoryTransaction.type == 'OUT',
            InventoryTransaction.date >= window_start
        )
        .group_by(InventoryTransaction.product_id)
        .all()
    )

    # Cálculo: tasa diaria → punto de reorden = tasa × (lead + safety)
    # Safety stock = 50% del lead time (conservador)
    suggestions = []
    for p in products:
        qty_out = float(out_by_product.get(p.id, 0) or 0)
        daily_rate = qty_out / window_days if window_days > 0 else 0
        safety_days = max(1, int(round(lead_days * 0.5)))
        reorder_point = daily_rate * (lead_days + safety_days)
        target_stock = daily_rate * (lead_days + target_days)
        stock = p.current_stock or 0

        # ¿Reponer?
        triggers_min = (p.min_stock_level or 0) > 0 and stock <= (p.min_stock_level or 0)
        triggers_rop = daily_rate > 0 and stock <= reorder_point
        should_reorder = triggers_min or triggers_rop

        # Cantidad sugerida
        suggested_qty = 0
        if should_reorder:
            if daily_rate > 0:
                suggested_qty = max(0, int(round(target_stock - stock)))
            # Si solo dispara min_stock pero sin movimiento, usar min_stock × 2 - current
            if suggested_qty <= 0 and triggers_min:
                suggested_qty = max(1, ((p.min_stock_level or 1) * 2) - stock)

        # Días de stock restantes
        days_left = (stock / daily_rate) if daily_rate > 0 else None

        # Urgencia
        if stock <= 0 and (qty_out > 0 or (p.min_stock_level or 0) > 0):
            urgency = 'critical'
        elif daily_rate > 0 and days_left is not None and days_left <= lead_days:
            urgency = 'critical'
        elif triggers_min:
            urgency = 'high'
        elif triggers_rop:
            urgency = 'medium'
        else:
            urgency = 'ok'

        suggestions.append({
            'product': p,
            'stock': stock,
            'min_stock': p.min_stock_level or 0,
            'qty_out': int(qty_out),
            'daily_rate': daily_rate,
            'monthly_rate': daily_rate * 30,
            'reorder_point': reorder_point,
            'target_stock': target_stock,
            'suggested_qty': suggested_qty,
            'estimated_cost': suggested_qty * (p.cost_price or 0),
            'days_left': days_left,
            'should_reorder': should_reorder,
            'urgency': urgency,
            'supplier': p.preferred_supplier,
            'supplier_name': p.preferred_supplier.business_name if p.preferred_supplier else None,
        })

    # Ordenar: críticos primero, luego por costo estimado descendente
    urgency_order = {'critical': 0, 'high': 1, 'medium': 2, 'ok': 3}
    suggestions.sort(key=lambda r: (urgency_order[r['urgency']], -r['estimated_cost']))

    # Resumen
    to_reorder = [s for s in suggestions if s['should_reorder']]
    summary = {
        'critical':  sum(1 for s in suggestions if s['urgency'] == 'critical'),
        'high':      sum(1 for s in suggestions if s['urgency'] == 'high'),
        'medium':    sum(1 for s in suggestions if s['urgency'] == 'medium'),
        'ok':        sum(1 for s in suggestions if s['urgency'] == 'ok'),
        'to_reorder_count': len(to_reorder),
        'estimated_total': sum(s['estimated_cost'] for s in to_reorder),
    }

    # Agrupar por proveedor
    from collections import OrderedDict
    by_supplier = OrderedDict()
    for s in to_reorder:
        key = s['supplier'].id if s['supplier'] else None
        if key not in by_supplier:
            by_supplier[key] = {
                'supplier': s['supplier'],
                'supplier_name': s['supplier_name'] or 'Sin proveedor preferente',
                'items': [],
                'total': 0,
            }
        by_supplier[key]['items'].append(s)
        by_supplier[key]['total'] += s['estimated_cost']

    return render_template(
        'inventory/reorder.html',
        company=company,
        suggestions=suggestions,
        summary=summary,
        by_supplier=list(by_supplier.values()),
        lead_days=lead_days,
        window_days=window_days,
        target_days=target_days,
    )

@inventory_bp.route('/companies/<int:company_id>/inventory/labels')
@inventory_admin_required
def inventory_labels(company_id):
    """Etiquetas imprimibles con QR por lote."""
    company = Company.query.get_or_404(company_id)

    # Modo: 'batches' (lotes) o 'products' (productos sin lote)
    mode = request.args.get('mode', 'batches')
    size = request.args.get('size', 'medium')  # small | medium | large
    if size not in ('small', 'medium', 'large'):
        size = 'medium'

    # Parámetros: filtros
    product_filter = request.args.get('product_id', type=int)
    batch_ids_raw = request.args.get('batch_ids', '')

    # IDs específicos
    batch_id_list = []
    if batch_ids_raw:
        for x in batch_ids_raw.split(','):
            x = x.strip()
            if x.isdigit():
                batch_id_list.append(int(x))

    from services.qr_service import QRService

    labels = []

    if mode == 'batches':
        q = (db.session.query(ProductBatch, Product)
             .join(Product, ProductBatch.product_id == Product.id)
             .filter(Product.company_id == company_id, ProductBatch.current_stock > 0))
        if product_filter:
            q = q.filter(Product.id == product_filter)
        if batch_id_list:
            q = q.filter(ProductBatch.id.in_(batch_id_list))
        q = q.order_by(Product.name, ProductBatch.expiration_date)
        for batch, p in q.all():
            qr_payload = '|'.join([
                'L', str(company_id), str(p.id), str(batch.id),
                p.sku or '', batch.batch_number or '',
                batch.expiration_date.strftime('%Y%m%d') if batch.expiration_date else ''
            ])
            qr_b64 = QRService.generate_qr_base64(qr_payload, size=4, border=2)
            labels.append({
                'kind': 'batch',
                'product': p,
                'batch': batch,
                'qr': qr_b64,
                'qr_data': qr_payload,
                'title': p.name,
                'sku': p.sku,
                'batch_number': batch.batch_number,
                'expiration': batch.expiration_date,
                'stock': batch.current_stock,
                'is_controlled': p.is_controlled,
            })
    else:  # products
        q = Product.query.filter_by(company_id=company_id, active=True).order_by(Product.name)
        if product_filter:
            q = q.filter(Product.id == product_filter)
        for p in q.all():
            qr_payload = '|'.join(['P', str(company_id), str(p.id), p.sku or ''])
            qr_b64 = QRService.generate_qr_base64(qr_payload, size=4, border=2)
            labels.append({
                'kind': 'product',
                'product': p,
                'batch': None,
                'qr': qr_b64,
                'qr_data': qr_payload,
                'title': p.name,
                'sku': p.sku,
                'batch_number': None,
                'expiration': None,
                'stock': p.current_stock,
                'is_controlled': p.is_controlled,
            })

    # Productos disponibles para el selector
    all_products = Product.query.filter_by(company_id=company_id, active=True).order_by(Product.name).all()

    return render_template(
        'inventory/labels.html',
        company=company,
        labels=labels,
        mode=mode,
        size=size,
        product_filter=product_filter,
        all_products=all_products,
    )

@inventory_bp.route('/companies/<int:company_id>/inventory/cycle-count', methods=['GET', 'POST'])
@inventory_admin_required
def inventory_cycle_count(company_id):
    """Conteo cíclico de inventario en web."""
    company = Company.query.get_or_404(company_id)

    if request.method == 'POST':
        import json as _json
        items_raw = request.form.get('items_json', '')
        try:
            items = _json.loads(items_raw) if items_raw else []
        except (ValueError, TypeError):
            items = []

        if not items:
            flash('No se enviaron productos para aplicar.', 'warning')
            return redirect(url_for('inventory.inventory_cycle_count', company_id=company_id))

        applied = 0
        skipped = 0
        for item in items:
            pid = item.get('product_id')
            actual = item.get('actual_stock')
            if pid is None or actual is None:
                skipped += 1
                continue
            try:
                actual = int(actual)
            except (TypeError, ValueError):
                skipped += 1
                continue
            if actual < 0:
                skipped += 1
                continue

            product = db.session.get(Product, pid)
            if not product or product.company_id != company_id or not product.active:
                skipped += 1
                continue

            previous = product.current_stock or 0
            diff = actual - previous
            if diff == 0:
                skipped += 1
                continue

            product.current_stock = actual
            tx = InventoryTransaction(
                product_id=pid,
                type='ADJUSTMENT',
                quantity=abs(diff),
                previous_stock=previous,
                new_stock=actual,
                reference='Conteo Cíclico Web',
                notes=f'Esperado: {previous}, Contado: {actual}, Dif: {diff:+d}',
                created_by_id=current_user.id
            )
            db.session.add(tx)
            applied += 1

        db.session.commit()
        flash(f'Conteo aplicado: {applied} ajustes, {skipped} sin cambios.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id))

    # GET: mostrar formulario
    category_filter = request.args.get('category', type=int)
    only_low = request.args.get('only_low') == '1'

    q = Product.query.filter_by(company_id=company_id, active=True)
    if category_filter:
        q = q.filter(Product.category_id == category_filter)
    if only_low:
        q = q.filter(Product.current_stock <= Product.min_stock_level)
    products = q.order_by(Product.name).all()

    categories = ProductCategory.query.filter_by(company_id=company_id).order_by(ProductCategory.name).all()

    return render_template(
        'inventory/cycle_count.html',
        company=company,
        products=products,
        categories=categories,
        category_filter=category_filter,
        only_low=only_low,
    )

@inventory_bp.route('/api/companies/<int:company_id>/inventory/search')
@login_required
def api_global_product_search(company_id):
    """Búsqueda global de productos para autocomplete del navbar."""
    if not current_user.can_access_company(company_id) and not current_user.is_admin:
        return jsonify({'results': []}), 403

    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'results': []})

    from sqlalchemy import or_ as _or
    like = f'%{q}%'
    products = (Product.query
                .filter(Product.company_id == company_id, Product.active == True)
                .filter(_or(
                    Product.name.ilike(like),
                    Product.sku.ilike(like),
                    Product.description.ilike(like),
                ))
                .order_by(Product.name)
                .limit(15)
                .all())

    results = []
    for p in products:
        results.append({
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'stock': p.current_stock,
            'min_stock': p.min_stock_level,
            'is_low': (p.min_stock_level or 0) > 0 and (p.current_stock or 0) <= (p.min_stock_level or 0),
            'url': url_for('inventory.product_history', company_id=company_id, product_id=p.id),
        })
    return jsonify({'results': results, 'query': q})

@inventory_bp.route('/companies/<int:company_id>/inventory/<int:product_id>/batches')
@login_required
def product_batches(company_id, product_id):
    """List batches for a product"""
    company = Company.query.get_or_404(company_id)
    product = Product.query.get_or_404(product_id)
    
    if product.company_id != company_id:
        return redirect(url_for('inventory.inventory_list', company_id=company_id))
        
    today = now_mexico().date()
    batches = ProductBatch.query.filter_by(product_id=product_id).order_by(ProductBatch.expiration_date).all()
    
    return render_template('inventory/batches.html', 
                         company=company, 
                         product=product, 
                         batches=batches, 
                         today=today)

@inventory_bp.route('/companies/<int:company_id>/inventory/<int:product_id>/receive', methods=['GET', 'POST'])
@inventory_admin_required
def receive_batch(company_id, product_id):
    """Recibir stock con lote y caducidad"""
    company = Company.query.get_or_404(company_id)
    product = Product.query.get_or_404(product_id)
    
    if product.company_id != company_id:
        return redirect(url_for('inventory.inventory_list', company_id=company_id))
        
    form = BatchForm()
    
    if form.validate_on_submit():
        quantity = form.quantity.data
        
        # Create Batch
        batch = ProductBatch(
            product_id=product.id,
            batch_number=form.batch_number.data,
            expiration_date=form.expiration_date.data,
            initial_stock=quantity,
            current_stock=quantity,
            acquisition_date=form.acquisition_date.data
        )
        db.session.add(batch)
        db.session.flush()
        
        # Create Transaction
        transaction = InventoryTransaction(
            product_id=product.id,
            batch_id=batch.id,
            type='IN',
            quantity=quantity,
            previous_stock=product.current_stock,
            new_stock=product.current_stock + quantity,
            reference=f'Recibo Lote {batch.batch_number}',
            notes='Recepción de stock con lote',
            created_by_id=current_user.id
        )
        db.session.add(transaction)
        
        # Update Product Total Stock
        product.current_stock += quantity
        
        db.session.commit()
        flash(f'Lote {batch.batch_number} registrado correctamente.', 'success')
        return redirect(url_for('inventory.product_batches', company_id=company_id, product_id=product_id))
        
    return render_template('inventory/receive_batch.html', company=company, product=product, form=form)

@inventory_bp.route('/companies/<int:company_id>/inventory/laboratories/add', methods=['GET', 'POST'])
@inventory_admin_required
def add_laboratory(company_id):
    """Agregar nuevo laboratorio"""
    company = Company.query.get_or_404(company_id)
    form = LaboratoryForm()

    if form.validate_on_submit():
        laboratory = Laboratory(
            company_id=company_id,
            name=form.name.data,
            sanitary_registration=form.sanitary_registration.data
        )
        db.session.add(laboratory)
        db.session.commit()
        flash(f'Laboratorio "{laboratory.name}" agregado correctamente.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='laboratories'))

    return render_template('inventory/laboratory_form.html', company=company, form=form, action='crear')

@inventory_bp.route('/companies/<int:company_id>/inventory/laboratories/<int:laboratory_id>/edit', methods=['GET', 'POST'])
@inventory_admin_required
def edit_laboratory(company_id, laboratory_id):
    """Editar laboratorio"""
    company = Company.query.get_or_404(company_id)
    laboratory = Laboratory.query.get_or_404(laboratory_id)

    if laboratory.company_id != company_id:
        flash('Laboratorio no encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='laboratories'))

    form = LaboratoryForm(obj=laboratory)

    if form.validate_on_submit():
        form.populate_obj(laboratory)
        db.session.commit()
        flash(f'Laboratorio "{laboratory.name}" actualizado.', 'success')
        return redirect(url_for('inventory.edit_laboratory', company_id=company_id, laboratory_id=laboratory_id))

    registrations = LaboratorySanitaryRegistration.query.filter_by(
        laboratory_id=laboratory_id
    ).order_by(LaboratorySanitaryRegistration.registration_number).all()

    return render_template('inventory/laboratory_form.html', company=company, form=form,
                           laboratory=laboratory, action='editar', registrations=registrations)

@inventory_bp.route('/companies/<int:company_id>/inventory/laboratories/<int:laboratory_id>/registrations/add', methods=['POST'])
@inventory_admin_required
def add_lab_registration(company_id, laboratory_id):
    """Agregar registro sanitario a laboratorio"""
    laboratory = Laboratory.query.get_or_404(laboratory_id)
    if laboratory.company_id != company_id:
        flash('Laboratorio no encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='laboratories'))

    reg_number = request.form.get('registration_number', '').strip()
    description = request.form.get('description', '').strip()

    if not reg_number:
        flash('El número de registro sanitario es requerido.', 'error')
    else:
        reg = LaboratorySanitaryRegistration(
            laboratory_id=laboratory_id,
            registration_number=reg_number,
            description=description or None
        )
        db.session.add(reg)
        db.session.commit()
        flash(f'Registro sanitario "{reg_number}" agregado.', 'success')

    return redirect(url_for('inventory.edit_laboratory', company_id=company_id, laboratory_id=laboratory_id))

@inventory_bp.route('/companies/<int:company_id>/inventory/laboratories/<int:laboratory_id>/registrations/<int:reg_id>/delete', methods=['POST'])
@inventory_admin_required
def delete_lab_registration(company_id, laboratory_id, reg_id):
    """Eliminar registro sanitario de laboratorio"""
    reg = LaboratorySanitaryRegistration.query.get_or_404(reg_id)
    if reg.laboratory_id != laboratory_id:
        flash('Registro no encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='laboratories'))

    reg_number = reg.registration_number
    db.session.delete(reg)
    db.session.commit()
    flash(f'Registro sanitario "{reg_number}" eliminado.', 'success')
    return redirect(url_for('inventory.edit_laboratory', company_id=company_id, laboratory_id=laboratory_id))

@inventory_bp.route('/api/laboratory/<int:laboratory_id>/registrations')
@login_required
def get_lab_registrations(laboratory_id):
    """API: obtener registros sanitarios de un laboratorio"""
    regs = LaboratorySanitaryRegistration.query.filter_by(
        laboratory_id=laboratory_id, active=True
    ).order_by(LaboratorySanitaryRegistration.registration_number).all()
    return jsonify([{
        'id': r.id,
        'registration_number': r.registration_number,
        'description': r.description
    } for r in regs])

@inventory_bp.route('/companies/<int:company_id>/inventory/categories/add', methods=['POST'])
@inventory_admin_required
def add_product_category(company_id):
    """Agregar nueva categoría de producto"""
    company = Company.query.get_or_404(company_id)
    form = ProductCategoryForm()

    if form.validate_on_submit():
        # Verificar nombre único
        existing = ProductCategory.query.filter_by(company_id=company_id, name=form.name.data).first()
        if existing:
            flash(f'Ya existe una categoría con el nombre "{form.name.data}".', 'error')
            return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='categories'))

        category = ProductCategory(
            company_id=company_id,
            name=form.name.data,
            description=form.description.data,
            requires_cofepris=form.requires_cofepris.data,
            requires_batch_tracking=form.requires_batch_tracking.data
        )
        db.session.add(category)
        db.session.commit()
        flash(f'Categoría "{category.name}" creada correctamente.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{error}', 'error')

    return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='categories'))

@inventory_bp.route('/companies/<int:company_id>/inventory/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@inventory_admin_required
def edit_product_category(company_id, category_id):
    """Editar categoría de producto"""
    company = Company.query.get_or_404(company_id)
    category = ProductCategory.query.get_or_404(category_id)

    if category.company_id != company_id:
        flash('Categoría no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='categories'))

    form = ProductCategoryForm(obj=category)

    if form.validate_on_submit():
        category.name = form.name.data
        category.description = form.description.data
        category.requires_cofepris = form.requires_cofepris.data
        category.requires_batch_tracking = form.requires_batch_tracking.data
        db.session.commit()
        flash(f'Categoría "{category.name}" actualizada.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='categories'))

    return render_template('inventory/category_form.html', company=company, form=form, category=category)

@inventory_bp.route('/companies/<int:company_id>/inventory/categories/<int:category_id>/toggle', methods=['POST'])
@inventory_admin_required
def toggle_product_category(company_id, category_id):
    """Activar/desactivar categoría de producto"""
    company = Company.query.get_or_404(company_id)
    category = ProductCategory.query.get_or_404(category_id)

    if category.company_id != company_id:
        flash('Categoría no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='categories'))

    category.active = not category.active
    db.session.commit()
    status = 'activada' if category.active else 'desactivada'
    flash(f'Categoría "{category.name}" {status}.', 'success')
    return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='categories'))

@inventory_bp.route('/api/product-category/<int:category_id>')
@login_required
def get_product_category_info(category_id):
    """API: obtener info de categoría para JS dinámico"""
    cat = ProductCategory.query.get_or_404(category_id)
    return jsonify({
        'id': cat.id,
        'name': cat.name,
        'requires_cofepris': cat.requires_cofepris,
        'requires_batch_tracking': cat.requires_batch_tracking,
    })

@inventory_bp.route('/companies/<int:company_id>/inventory/services/add', methods=['GET', 'POST'])
@inventory_admin_required
def add_service(company_id):
    """Agregar nuevo servicio"""
    company = Company.query.get_or_404(company_id)
    form = ServiceForm()

    if form.validate_on_submit():
        service = Service(
            company_id=company_id,
            name=form.name.data,
            description=form.description.data,
            price=form.price.data or 0,
            sat_key=form.sat_key.data or '01010101',
            sat_unit_key=form.sat_unit_key.data or 'E48'
        )
        db.session.add(service)
        db.session.commit()
        flash(f'Servicio "{service.name}" agregado correctamente.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='services'))

    return render_template('inventory/service_form.html', company=company, form=form, action='crear')

@inventory_bp.route('/companies/<int:company_id>/inventory/services/<int:service_id>/edit', methods=['GET', 'POST'])
@inventory_admin_required
def edit_service(company_id, service_id):
    """Editar servicio"""
    company = Company.query.get_or_404(company_id)
    service = Service.query.get_or_404(service_id)

    if service.company_id != company_id:
        flash('Servicio no encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='services'))

    form = ServiceForm(obj=service)

    if form.validate_on_submit():
        form.populate_obj(service)
        db.session.commit()
        flash(f'Servicio "{service.name}" actualizado.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='services'))

    return render_template('inventory/service_form.html', company=company, form=form, service=service, action='editar')

@inventory_bp.route('/companies/<int:company_id>/inventory/suppliers/add', methods=['GET', 'POST'])
@inventory_admin_required
def add_supplier_manual(company_id):
    """Agregar proveedor manualmente"""
    company = Company.query.get_or_404(company_id)
    form = SupplierManualForm()

    if form.validate_on_submit():
        # Verificar si ya existe
        existing = Supplier.query.filter_by(company_id=company_id, rfc=form.rfc.data.upper()).first()
        if existing:
            flash(f'Ya existe un proveedor con RFC {form.rfc.data.upper()}.', 'warning')
            return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='suppliers'))

        supplier = Supplier(
            company_id=company_id,
            rfc=form.rfc.data.upper(),
            business_name=form.business_name.data,
            commercial_name=form.commercial_name.data,
            contact_name=form.contact_name.data,
            email=form.email.data,
            phone=form.phone.data,
            address=form.address.data,
            payment_terms=form.payment_terms.data,
            notes=form.notes.data,
            is_medication_supplier=form.is_medication_supplier.data,
            sanitary_registration=form.sanitary_registration.data
        )
        db.session.add(supplier)
        db.session.commit()
        flash(f'Proveedor "{supplier.business_name}" agregado correctamente.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='suppliers'))

    return render_template('inventory/supplier_form.html', company=company, form=form, action='crear')

@inventory_bp.route('/companies/<int:company_id>/inventory/suppliers/<int:supplier_id>/edit', methods=['GET', 'POST'])
@inventory_admin_required
def edit_supplier_inventory(company_id, supplier_id):
    """Editar proveedor desde inventario"""
    company = Company.query.get_or_404(company_id)
    supplier = Supplier.query.get_or_404(supplier_id)

    if supplier.company_id != company_id:
        flash('Proveedor no encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='suppliers'))

    form = SupplierManualForm(obj=supplier)

    if form.validate_on_submit():
        supplier.business_name = form.business_name.data
        supplier.commercial_name = form.commercial_name.data
        supplier.contact_name = form.contact_name.data
        supplier.email = form.email.data
        supplier.phone = form.phone.data
        supplier.address = form.address.data
        supplier.payment_terms = form.payment_terms.data
        supplier.notes = form.notes.data
        supplier.is_medication_supplier = form.is_medication_supplier.data
        supplier.sanitary_registration = form.sanitary_registration.data
        db.session.commit()
        flash(f'Proveedor "{supplier.business_name}" actualizado.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='suppliers'))

    return render_template('inventory/supplier_form.html', company=company, form=form, supplier=supplier, action='editar')

@inventory_bp.route('/companies/<int:company_id>/inventory/orders/add', methods=['GET', 'POST'])
@inventory_admin_required
def add_purchase_order(company_id):
    """Crear nueva orden de compra"""
    company = Company.query.get_or_404(company_id)
    form = PurchaseOrderForm()

    # Cargar proveedores para el select
    suppliers = Supplier.query.filter_by(company_id=company_id, active=True).order_by(Supplier.business_name).all()
    form.supplier_id.choices = [(0, '-- Seleccionar Proveedor --')] + [(s.id, f"{s.business_name} ({s.rfc})") for s in suppliers]

    if form.validate_on_submit():
        order = PurchaseOrder(
            company_id=company_id,
            supplier_id=form.supplier_id.data,
            status='DRAFT',
            notes=form.notes.data
        )
        db.session.add(order)
        db.session.commit()
        flash('Orden de compra creada. Agregue los productos.', 'success')
        return redirect(url_for('inventory.edit_purchase_order', company_id=company_id, order_id=order.id))

    return render_template('inventory/purchase_order_form.html', company=company, form=form, action='crear')

@inventory_bp.route('/companies/<int:company_id>/inventory/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@inventory_admin_required
def edit_purchase_order(company_id, order_id):
    """Editar orden de compra (agregar/quitar productos)"""
    company = Company.query.get_or_404(company_id)
    order = PurchaseOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

    if order.status not in ['DRAFT', 'SENT']:
        flash('Esta orden no se puede editar.', 'warning')
        return redirect(url_for('inventory.view_purchase_order', company_id=company_id, order_id=order_id))

    # Cargar productos disponibles
    products = Product.query.filter_by(company_id=company_id, active=True).order_by(Product.name).all()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_product':
            product_id = int(request.form.get('product_id'))
            unit_cost = float(request.form.get('unit_cost', 0))
            order_unit = request.form.get('order_unit', 'UNIDAD')

            product_obj = Product.query.get(product_id)
            upp = product_obj.units_per_package or 1

            if order_unit == 'PAQUETE' and upp > 1:
                pkg_qty = int(request.form.get('package_quantity') or 0)
                loose_qty = int(request.form.get('loose_quantity') or 0)
                quantity = (pkg_qty * upp) + loose_qty
            else:
                order_unit = 'UNIDAD'
                quantity = int(request.form.get('quantity', 1))
                pkg_qty = None
                loose_qty = 0

            detail = PurchaseOrderDetail(
                order_id=order.id,
                product_id=product_id,
                quantity_requested=quantity,
                unit_cost=unit_cost,
                order_unit=order_unit,
                package_quantity=pkg_qty,
                loose_quantity=loose_qty
            )
            db.session.add(detail)

            # Actualizar costo del producto con el nuevo precio
            if unit_cost > 0:
                product_obj.cost_price = unit_cost

        elif action == 'update_cost':
            detail_id = int(request.form.get('detail_id'))
            new_cost = float(request.form.get('new_cost', 0))
            detail = PurchaseOrderDetail.query.get(detail_id)
            if detail and detail.order_id == order.id:
                detail.unit_cost = new_cost
                # También actualizar el costo del producto
                if new_cost > 0:
                    detail.product.cost_price = new_cost

        elif action == 'remove_product':
            detail_id = int(request.form.get('detail_id'))
            detail = PurchaseOrderDetail.query.get(detail_id)
            if detail and detail.order_id == order.id:
                db.session.delete(detail)

        elif action == 'send_order':
            order.status = 'SENT'
            order.sent_at = now_mexico()
            flash('Orden enviada correctamente.', 'success')

        # Recalcular total estimado
        order.estimated_total = sum(d.quantity_requested * d.unit_cost for d in order.details)
        db.session.commit()

        if action == 'send_order':
            return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

    return render_template('inventory/purchase_order_edit.html', company=company, order=order, products=products)

@inventory_bp.route('/companies/<int:company_id>/inventory/orders/<int:order_id>/view')
@login_required
def view_purchase_order(company_id, order_id):
    """Ver detalles de orden de compra"""
    company = Company.query.get_or_404(company_id)
    order = PurchaseOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

    return render_template('inventory/purchase_order_view.html', company=company, order=order)

@inventory_bp.route('/companies/<int:company_id>/inventory/orders/<int:order_id>/pdf')
@login_required
def purchase_order_pdf(company_id, order_id):
    """Generar PDF de orden de compra"""
    from flask import render_template, send_file, abort
    from io import BytesIO
    import weasyprint
    import base64
    import mimetypes

    company = Company.query.get_or_404(company_id)
    order = PurchaseOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

    # Cargar logo como base64
    logo_data_uri = None
    if company.logo_path:
        resolved_logo = None
        if os.path.exists(company.logo_path):
            resolved_logo = company.logo_path
        else:
            fallback = os.path.join(PROJECT_ROOT, 'logos', os.path.basename(company.logo_path.replace('\\', '/')))
            if os.path.exists(fallback):
                resolved_logo = fallback
        
        if resolved_logo:
            try:
                with open(resolved_logo, 'rb') as lf:
                    logo_b64 = base64.b64encode(lf.read()).decode('ascii')
                mime = mimetypes.guess_type(resolved_logo)[0] or 'image/png'
                logo_data_uri = f"data:{mime};base64,{logo_b64}"
            except Exception as e:
                logger.error(f"Error loading logo for purchase order PDF: {e}")

    html_string = render_template('inventory/purchase_order_pdf.html', company=company, order=order, logo_data_uri=logo_data_uri)
    pdf_bytes = weasyprint.HTML(string=html_string).write_pdf()

    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Orden_Compra_{order.id}.pdf"
    )

@inventory_bp.route('/companies/<int:company_id>/inventory/orders/<int:order_id>/review', methods=['GET', 'POST'])
@inventory_admin_required
def review_purchase_order(company_id, order_id):
    """Revisar/recibir orden de compra (Fase 2)"""
    company = Company.query.get_or_404(company_id)
    order = PurchaseOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

    if order.status not in ['SENT', 'IN_REVIEW']:
        flash('Esta orden no puede ser revisada en este momento.', 'warning')
        return redirect(url_for('inventory.view_purchase_order', company_id=company_id, order_id=order_id))

    if request.method == 'POST':
        # Actualizar cantidades recibidas y datos de lote
        for detail in order.details:
            product_obj = detail.product
            upp = product_obj.units_per_package or 1

            # Manejar recepción por paquete o unidad
            if detail.order_unit == 'PAQUETE' and upp > 1:
                pkgs = int(request.form.get(f'packages_received_{detail.id}') or 0)
                loose = int(request.form.get(f'loose_received_{detail.id}') or 0)
                detail.packages_received = pkgs
                detail.loose_received = loose
                detail.quantity_received = (pkgs * upp) + loose
            else:
                received = request.form.get(f'received_{detail.id}')
                if received is not None:
                    detail.quantity_received = int(received or 0)

            # Lote y caducidad solo si la categoría lo requiere
            requires_batch = (product_obj.category and product_obj.category.requires_batch_tracking)
            if requires_batch:
                batch_number = request.form.get(f'batch_{detail.id}')
                expiration_str = request.form.get(f'expiration_{detail.id}')
                detail.batch_number = batch_number if batch_number else None
                if expiration_str:
                    detail.expiration_date = datetime.strptime(expiration_str, '%Y-%m-%d').date()
                else:
                    detail.expiration_date = None
            else:
                detail.batch_number = None
                detail.expiration_date = None

        order.status = 'IN_REVIEW'
        order.received_at = now_mexico()
        db.session.commit()
        flash('Datos de recepcion actualizados.', 'success')
        return redirect(url_for('inventory.complete_purchase_order', company_id=company_id, order_id=order_id))

    return render_template('inventory/purchase_order_review.html', company=company, order=order)

@inventory_bp.route('/companies/<int:company_id>/inventory/orders/<int:order_id>/complete', methods=['GET', 'POST'])
@inventory_admin_required
def complete_purchase_order(company_id, order_id):
    """Completar orden de compra (Fase 3) - Ajustar inventario"""
    company = Company.query.get_or_404(company_id)
    order = PurchaseOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

    if order.status != 'IN_REVIEW':
        flash('Esta orden no puede ser completada en este momento.', 'warning')
        return redirect(url_for('inventory.view_purchase_order', company_id=company_id, order_id=order_id))

    if request.method == 'POST':
        # Actualizar inventario con las cantidades recibidas
        for detail in order.details:
            if detail.quantity_received > 0:
                product = detail.product
                previous_stock = product.current_stock
                batch_id = None

                # Crear lote solo si la categoría requiere batch tracking y hay datos de lote
                requires_batch = (product.category and product.category.requires_batch_tracking)
                if requires_batch and detail.batch_number:
                    batch = ProductBatch(
                        product_id=product.id,
                        batch_number=detail.batch_number,
                        expiration_date=detail.expiration_date,
                        initial_stock=detail.quantity_received,
                        current_stock=detail.quantity_received,
                        acquisition_date=now_mexico().date()
                    )
                    db.session.add(batch)
                    db.session.flush()
                    batch_id = batch.id

                # Crear transaccion de inventario
                notes_parts = ['Recepcion de orden de compra']
                if detail.batch_number:
                    notes_parts.append(f'Lote: {detail.batch_number}')
                if detail.order_unit == 'PAQUETE' and (product.units_per_package or 1) > 1:
                    notes_parts.append(f'{detail.packages_received or 0} {product.packaging_type or "paq"} + {detail.loose_received or 0} pzas sueltas')

                transaction = InventoryTransaction(
                    product_id=product.id,
                    batch_id=batch_id,
                    type='IN',
                    quantity=detail.quantity_received,
                    previous_stock=previous_stock,
                    new_stock=previous_stock + detail.quantity_received,
                    reference=f'Orden Compra #{order.id}',
                    notes=' - '.join(notes_parts),
                    created_by_id=current_user.id
                )
                db.session.add(transaction)

                # Actualizar stock del producto
                product.current_stock += detail.quantity_received

        order.status = 'COMPLETED'
        order.completed_at = now_mexico()
        db.session.commit()
        flash('Orden completada. El inventario ha sido actualizado.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

    return render_template('inventory/purchase_order_complete.html', company=company, order=order)

@inventory_bp.route('/companies/<int:company_id>/inventory/orders/<int:order_id>/delete', methods=['POST'])
@inventory_admin_required
def delete_purchase_order(company_id, order_id):
    """Eliminar orden de compra"""
    company = Company.query.get_or_404(company_id)
    order = PurchaseOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

    # Guardar el nombre del proveedor antes de eliminar
    supplier_name = order.supplier.business_name if order.supplier else f"#{order_id}"

    # Eliminar la orden (los detalles se eliminan automáticamente por cascade)
    db.session.delete(order)
    db.session.commit()

    flash(f'Orden para {supplier_name} eliminada correctamente.', 'success')
    return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='orders'))

@inventory_bp.route('/companies/<int:company_id>/inventory/exits/add', methods=['GET', 'POST'])
@inventory_admin_required
def add_exit_order(company_id):
    """Crear nueva orden de salida"""
    company = Company.query.get_or_404(company_id)
    form = ExitOrderForm()

    if form.validate_on_submit():
        order = ExitOrder(
            company_id=company_id,
            recipient_name=form.recipient_name.data,
            recipient_type=form.recipient_type.data,
            recipient_id=form.recipient_id.data,
            notes=form.notes.data,
            created_by_id=current_user.id
        )
        db.session.add(order)
        db.session.commit()
        flash('Orden de salida creada. Agregue los productos.', 'success')
        return redirect(url_for('inventory.edit_exit_order', company_id=company_id, order_id=order.id))

    return render_template('inventory/exit_order_form.html', company=company, form=form, action='crear')

@inventory_bp.route('/companies/<int:company_id>/inventory/exits/<int:order_id>/edit', methods=['GET', 'POST'])
@inventory_admin_required
def edit_exit_order(company_id, order_id):
    """Editar orden de salida (agregar productos)"""
    company = Company.query.get_or_404(company_id)
    order = ExitOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='exits'))

    if order.status != 'DRAFT':
        flash('Esta orden ya no puede ser editada.', 'warning')
        return redirect(url_for('inventory.view_exit_order', company_id=company_id, order_id=order_id))

    # Productos disponibles con stock
    products = Product.query.filter(
        Product.company_id == company_id,
        Product.active == True,
        Product.current_stock > 0
    ).order_by(Product.name).all()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_product':
            product_id = int(request.form.get('product_id'))
            quantity = int(request.form.get('quantity', 1))
            batch_id = request.form.get('batch_id')
            batch_id = int(batch_id) if batch_id else None

            product = Product.query.get(product_id)
            if product and quantity > 0:
                # Verificar stock disponible
                if quantity > product.current_stock:
                    flash(f'Stock insuficiente. Disponible: {product.current_stock}', 'error')
                else:
                    detail = ExitOrderDetail(
                        order_id=order.id,
                        product_id=product_id,
                        batch_id=batch_id,
                        quantity=quantity
                    )
                    db.session.add(detail)
                    db.session.commit()
                    flash(f'Producto agregado: {product.name} x{quantity}', 'success')

        elif action == 'remove_detail':
            detail_id = int(request.form.get('detail_id'))
            detail = ExitOrderDetail.query.get(detail_id)
            if detail and detail.order_id == order.id:
                db.session.delete(detail)
                db.session.commit()
                flash('Producto eliminado de la orden.', 'success')

        elif action == 'update_info':
            form = ExitOrderForm()
            order.recipient_name = form.recipient_name.data
            order.recipient_type = form.recipient_type.data
            order.recipient_id = form.recipient_id.data
            order.notes = form.notes.data
            db.session.commit()
            flash('Informacion actualizada.', 'success')

        return redirect(url_for('inventory.edit_exit_order', company_id=company_id, order_id=order_id))

    form = ExitOrderForm(obj=order)
    return render_template('inventory/exit_order_edit.html', company=company, order=order, form=form, products=products)

@inventory_bp.route('/companies/<int:company_id>/inventory/exits/<int:order_id>/complete', methods=['POST'])
@inventory_admin_required
def complete_exit_order(company_id, order_id):
    """Completar orden de salida - descuenta del inventario"""
    company = Company.query.get_or_404(company_id)
    order = ExitOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='exits'))

    if order.status != 'DRAFT':
        flash('Esta orden ya fue procesada.', 'warning')
        return redirect(url_for('inventory.view_exit_order', company_id=company_id, order_id=order_id))

    if not order.details:
        flash('No hay productos en la orden.', 'error')
        return redirect(url_for('inventory.edit_exit_order', company_id=company_id, order_id=order_id))

    # Verificar stock antes de procesar
    for detail in order.details:
        if detail.quantity > detail.product.current_stock:
            flash(f'Stock insuficiente para {detail.product.name}. Disponible: {detail.product.current_stock}', 'error')
            return redirect(url_for('inventory.edit_exit_order', company_id=company_id, order_id=order_id))

    # Procesar salidas
    for detail in order.details:
        product = detail.product
        previous_stock = product.current_stock

        # Crear transaccion de inventario
        transaction = InventoryTransaction(
            product_id=product.id,
            batch_id=detail.batch_id,
            type='OUT',
            quantity=detail.quantity,
            previous_stock=previous_stock,
            new_stock=previous_stock - detail.quantity,
            reference=f'Orden Salida #{order.id}',
            notes=f'Entrega a: {order.recipient_name}',
            created_by_id=current_user.id
        )
        db.session.add(transaction)

        # Actualizar stock del producto
        product.current_stock -= detail.quantity

        # Actualizar stock del lote si aplica
        if detail.batch_id and detail.batch:
            detail.batch.current_stock -= detail.quantity

    order.status = 'COMPLETED'
    order.completed_at = now_mexico()
    db.session.commit()

    flash(f'Orden #{order.id} completada. Inventario actualizado.', 'success')
    return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='exits'))

@inventory_bp.route('/companies/<int:company_id>/inventory/exits/<int:order_id>')
@login_required
def view_exit_order(company_id, order_id):
    """Ver detalle de orden de salida"""
    company = Company.query.get_or_404(company_id)
    order = ExitOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='exits'))

    return render_template('inventory/exit_order_view.html', company=company, order=order)

@inventory_bp.route('/companies/<int:company_id>/inventory/exits/<int:order_id>/delete', methods=['POST'])
@inventory_admin_required
def delete_exit_order(company_id, order_id):
    """Eliminar orden de salida (solo borradores)"""
    company = Company.query.get_or_404(company_id)
    order = ExitOrder.query.get_or_404(order_id)

    if order.company_id != company_id:
        flash('Orden no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='exits'))

    if order.status != 'DRAFT':
        flash('Solo se pueden eliminar ordenes en borrador.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='exits'))

    # Guardar el nombre del destinatario antes de eliminar
    recipient_name = order.recipient_name or f"#{order_id}"

    ExitOrderDetail.query.filter_by(order_id=order_id).delete()
    db.session.delete(order)
    db.session.commit()

    flash(f'Orden para {recipient_name} eliminada.', 'success')
    return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='exits'))

@inventory_bp.route('/api/companies/<int:company_id>/products/<int:product_id>/batches')
@login_required
def api_product_batches(company_id, product_id):
    """API para obtener lotes de un producto"""
    product = Product.query.get_or_404(product_id)
    if product.company_id != company_id:
        return jsonify([])

    batches = ProductBatch.query.filter(
        ProductBatch.product_id == product_id,
        ProductBatch.current_stock > 0,
        ProductBatch.is_active == True
    ).order_by(ProductBatch.expiration_date.asc()).all()

    return jsonify([{
        'id': b.id,
        'batch_number': b.batch_number,
        'expiration_date': b.expiration_date.strftime('%d/%m/%Y') if b.expiration_date else None,
        'current_stock': b.current_stock
    } for b in batches])

@inventory_bp.route('/companies/<int:company_id>/inventory/requests/initial-stock', methods=['GET', 'POST'])
@login_required
def create_initial_stock_request(company_id):
    """Crear solicitud de ingreso inicial de medicamentos"""
    company = Company.query.get_or_404(company_id)
    if not current_user.is_admin:
        perms = current_user.get_company_permissions(company_id)
        if not perms.get('perm_inventory'):
            flash('No tienes permisos de inventario para esta empresa.', 'error')
            return redirect(url_for('main.index'))

    form = InitialStockRequestForm()
    products = Product.query.filter_by(company_id=company_id, active=True).order_by(Product.name).all()
    form.product_id.choices = [(0, '-- Producto Nuevo --')] + [(p.id, p.name) for p in products]

    if form.validate_on_submit():
        inv_request = InventoryRequest(
            company_id=company_id,
            request_type='INITIAL_STOCK',
            status='PENDING',
            product_id=form.product_id.data if form.product_id.data and form.product_id.data != 0 else None,
            new_product_name=form.new_product_name.data if (not form.product_id.data or form.product_id.data == 0) else None,
            new_product_sku=form.new_product_sku.data if (not form.product_id.data or form.product_id.data == 0) else None,
            quantity=form.quantity.data,
            batch_number=form.batch_number.data,
            expiration_date=form.expiration_date.data,
            cost_price=form.cost_price.data,
            selling_price=form.selling_price.data,
            notes=form.notes.data,
            created_by_id=current_user.id,
            created_at=now_mexico()
        )
        db.session.add(inv_request)
        db.session.commit()
        flash('Solicitud de ingreso inicial enviada. Pendiente de aprobacion.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='requests'))

    return render_template('inventory/request_initial_stock.html', form=form, company=company)

@inventory_bp.route('/companies/<int:company_id>/inventory/requests/adjustment', methods=['GET', 'POST'])
@login_required
def create_adjustment_request(company_id):
    """Crear solicitud de ajuste de inventario"""
    company = Company.query.get_or_404(company_id)
    if not current_user.is_admin:
        perms = current_user.get_company_permissions(company_id)
        if not perms.get('perm_inventory'):
            flash('No tienes permisos de inventario para esta empresa.', 'error')
            return redirect(url_for('main.index'))

    form = AdjustmentRequestForm()
    products = Product.query.filter_by(company_id=company_id, active=True).order_by(Product.name).all()
    form.product_id.choices = [(p.id, f'{p.name} (Stock: {p.current_stock})') for p in products]

    # Mapa de stock para JavaScript
    products_stock = {p.id: p.current_stock for p in products}

    if form.validate_on_submit():
        product = Product.query.get_or_404(form.product_id.data)
        if product.company_id != company_id:
            flash('Producto no valido.', 'error')
            return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='requests'))

        current_stock = product.current_stock

        if form.adjustment_mode.data == 'CORRECT_STOCK':
            desired = form.desired_stock.data
            quantity = abs(desired - current_stock)
            direction = 'IN' if desired > current_stock else 'OUT'
        else:
            quantity = form.quantity.data
            direction = form.adjustment_direction.data
            desired = None

        inv_request = InventoryRequest(
            company_id=company_id,
            request_type='ADJUSTMENT',
            status='PENDING',
            product_id=product.id,
            quantity=quantity,
            adjustment_mode=form.adjustment_mode.data,
            adjustment_direction=direction,
            current_stock_snapshot=current_stock,
            desired_stock=desired,
            notes=form.notes.data,
            created_by_id=current_user.id,
            created_at=now_mexico()
        )
        db.session.add(inv_request)
        db.session.commit()
        flash('Solicitud de ajuste enviada. Pendiente de aprobacion.', 'success')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='requests'))

    return render_template('inventory/request_adjustment.html', form=form, company=company,
                           products_stock=products_stock)

@inventory_bp.route('/companies/<int:company_id>/inventory/requests/<int:request_id>')
@login_required
def view_inventory_request(company_id, request_id):
    """Ver detalle de solicitud de inventario"""
    company = Company.query.get_or_404(company_id)
    inv_request = InventoryRequest.query.get_or_404(request_id)

    if inv_request.company_id != company_id:
        flash('Solicitud no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='requests'))

    if not current_user.is_admin and inv_request.created_by_id != current_user.id:
        flash('No tienes permiso para ver esta solicitud.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='requests'))

    return render_template('inventory/request_detail.html', company=company, inv_request=inv_request)

@inventory_bp.route('/companies/<int:company_id>/inventory/requests/<int:request_id>/approve', methods=['POST'])
@inventory_admin_required
def approve_inventory_request(company_id, request_id):
    """Aprobar solicitud de inventario (solo admin)"""
    company = Company.query.get_or_404(company_id)
    inv_request = InventoryRequest.query.get_or_404(request_id)

    if inv_request.company_id != company_id:
        flash('Solicitud no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='requests'))

    if inv_request.status != 'PENDING':
        flash('Esta solicitud ya fue procesada.', 'error')
        return redirect(url_for('inventory.view_inventory_request', company_id=company_id, request_id=request_id))

    try:
        if inv_request.request_type == 'INITIAL_STOCK':
            # Obtener o crear producto
            if inv_request.product_id:
                product = Product.query.get(inv_request.product_id)
            else:
                product = Product(
                    company_id=company_id,
                    name=inv_request.new_product_name,
                    sku=inv_request.new_product_sku,
                    cost_price=inv_request.cost_price or 0.0,
                    selling_price=inv_request.selling_price or 0.0,
                    current_stock=0
                )
                db.session.add(product)
                db.session.flush()
                inv_request.product_id = product.id

            # Actualizar precios si se proporcionaron
            if inv_request.cost_price is not None:
                product.cost_price = inv_request.cost_price
            if inv_request.selling_price is not None:
                product.selling_price = inv_request.selling_price

            # Crear lote si hay datos
            batch = None
            if inv_request.batch_number:
                batch = ProductBatch(
                    product_id=product.id,
                    batch_number=inv_request.batch_number,
                    expiration_date=inv_request.expiration_date,
                    initial_stock=inv_request.quantity,
                    current_stock=inv_request.quantity,
                    acquisition_date=now_mexico().date()
                )
                db.session.add(batch)
                db.session.flush()

            # Crear transaccion
            previous_stock = product.current_stock
            product.current_stock += inv_request.quantity

            transaction = InventoryTransaction(
                product_id=product.id,
                batch_id=batch.id if batch else None,
                type='IN',
                quantity=inv_request.quantity,
                previous_stock=previous_stock,
                new_stock=product.current_stock,
                date=now_mexico(),
                reference=f'Solicitud Ingreso #{inv_request.id}',
                notes=f'[APROBADO: {current_user.username}] {inv_request.notes}',
                created_by_id=current_user.id
            )
            db.session.add(transaction)

        elif inv_request.request_type == 'ADJUSTMENT':
            product = Product.query.get(inv_request.product_id)
            previous_stock = product.current_stock

            if inv_request.adjustment_mode == 'CORRECT_STOCK':
                new_stock = inv_request.desired_stock
            elif inv_request.adjustment_direction == 'IN':
                new_stock = product.current_stock + inv_request.quantity
            else:
                new_stock = max(0, product.current_stock - inv_request.quantity)

            product.current_stock = new_stock

            transaction = InventoryTransaction(
                product_id=product.id,
                type='ADJUSTMENT',
                quantity=inv_request.quantity,
                previous_stock=previous_stock,
                new_stock=new_stock,
                date=now_mexico(),
                reference=f'Solicitud Ajuste #{inv_request.id}',
                notes=f'[APROBADO: {current_user.username}] {inv_request.notes}',
                created_by_id=current_user.id
            )
            db.session.add(transaction)

        inv_request.status = 'APPROVED'
        inv_request.reviewed_by_id = current_user.id
        inv_request.reviewed_at = now_mexico()
        db.session.commit()
        flash('Solicitud aprobada. El inventario ha sido actualizado.', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error al aprobar solicitud #{request_id}: {str(e)}')
        flash(f'Error al procesar la solicitud: {str(e)}', 'error')

    return redirect(url_for('inventory.view_inventory_request', company_id=company_id, request_id=request_id))

@inventory_bp.route('/companies/<int:company_id>/inventory/requests/<int:request_id>/reject', methods=['POST'])
@inventory_admin_required
def reject_inventory_request(company_id, request_id):
    """Rechazar solicitud de inventario (solo admin)"""
    company = Company.query.get_or_404(company_id)
    inv_request = InventoryRequest.query.get_or_404(request_id)

    if inv_request.company_id != company_id:
        flash('Solicitud no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='requests'))

    if inv_request.status != 'PENDING':
        flash('Esta solicitud ya fue procesada.', 'error')
        return redirect(url_for('inventory.view_inventory_request', company_id=company_id, request_id=request_id))

    inv_request.status = 'REJECTED'
    inv_request.reviewed_by_id = current_user.id
    inv_request.reviewed_at = now_mexico()
    inv_request.rejection_reason = request.form.get('rejection_reason', '').strip()
    db.session.commit()

    flash('Solicitud rechazada.', 'info')
    return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='requests'))

@inventory_bp.route('/companies/<int:company_id>/inventory/templates/add', methods=['GET', 'POST'])
@inventory_admin_required
def add_invoice_template(company_id):
    """Crear nueva plantilla de factura"""
    company = Company.query.get_or_404(company_id)
    form = InvoiceTemplateForm()

    if form.validate_on_submit():
        template = InvoiceTemplate(
            company_id=company_id,
            name=form.name.data,
            description=form.description.data
        )
        db.session.add(template)
        db.session.commit()
        flash('Plantilla creada. Agregue los items.', 'success')
        return redirect(url_for('inventory.edit_invoice_template', company_id=company_id, template_id=template.id))

    return render_template('inventory/template_form.html', company=company, form=form, action='crear')

@inventory_bp.route('/companies/<int:company_id>/inventory/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@inventory_admin_required
def edit_invoice_template(company_id, template_id):
    """Editar plantilla de factura (agregar/quitar items)"""
    company = Company.query.get_or_404(company_id)
    template = InvoiceTemplate.query.get_or_404(template_id)

    if template.company_id != company_id:
        flash('Plantilla no encontrada.', 'error')
        return redirect(url_for('inventory.inventory_list', company_id=company_id, tab='templates'))

    # Cargar productos y servicios
    products = Product.query.filter_by(company_id=company_id, active=True).order_by(Product.name).all()
    services = Service.query.filter_by(company_id=company_id, active=True).order_by(Service.name).all()

    form = InvoiceTemplateForm(obj=template)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_info':
            template.name = form.name.data
            template.description = form.description.data

        elif action == 'add_product':
            product_id = int(request.form.get('product_id'))
            quantity = float(request.form.get('quantity', 1))
            item = InvoiceTemplateItem(
                template_id=template.id,
                item_type='PRODUCT',
                product_id=product_id,
                quantity=quantity
            )
            db.session.add(item)

        elif action == 'add_service':
            service_id = int(request.form.get('service_id'))
            quantity = float(request.form.get('quantity', 1))
            item = InvoiceTemplateItem(
                template_id=template.id,
                item_type='SERVICE',
                service_id=service_id,
                quantity=quantity
            )
            db.session.add(item)

        elif action == 'remove_item':
            item_id = int(request.form.get('item_id'))
            item = InvoiceTemplateItem.query.get(item_id)
            if item and item.template_id == template.id:
                db.session.delete(item)

        db.session.commit()
        flash('Plantilla actualizada.', 'success')

    return render_template('inventory/template_edit.html', company=company, template=template,
                         products=products, services=services, form=form)

