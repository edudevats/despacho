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


invoicing_bp = Blueprint('invoicing', __name__)

@invoicing_bp.route('/sales')
@login_required
def sales_list():
    """Show list of companies for sales analysis"""
    companies_list = current_user.accessible_companies_with_perm('sales')
    return render_template('sales_list.html', companies=companies_list)

@invoicing_bp.route('/companies/<int:company_id>/sales')
@login_required
@require_company_perm('sales')
def sales_dashboard(company_id):
    """Dashboard de Análisis de Ventas con comparación año a año"""
    company = Company.query.get_or_404(company_id)
    
    today = now_mexico()
    
    # Get year parameters from query string, default to current and previous year
    current_year = request.args.get('current_year', type=int, default=today.year)
    previous_year = request.args.get('previous_year', type=int, default=today.year - 1)
    
    # Get available years from invoices
    available_years = db.session.query(
        extract('year', Invoice.date).label('year')
    ).filter(
        Invoice.company_id == company_id,
        Invoice.type == 'I'  # Only income invoices
    ).distinct().order_by(extract('year', Invoice.date).desc()).all()
    available_years = [int(y[0]) for y in available_years]
    
    # Monthly comparison data
    monthly_comparison = []
    month_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    # Chart data arrays
    chart_months = []
    chart_current_sales = []
    chart_previous_sales = []
    chart_growth_percentage = []
    
    # Annual totals
    annual_current_total = 0
    annual_previous_total = 0
    annual_current_invoices = 0
    annual_previous_invoices = 0
    
    for month_num in range(1, 13):
        # Current year sales
        current_sales_query = db.session.query(
            func.sum(Invoice.total).label('total'),
            func.count(Invoice.id).label('count')
        ).filter(
            Invoice.company_id == company_id,
            Invoice.type == 'I',
            extract('month', Invoice.date) == month_num,
            extract('year', Invoice.date) == current_year
        ).first()
        
        current_sales = float(current_sales_query.total or 0)
        current_invoices = int(current_sales_query.count or 0)
        
        # Previous year sales
        previous_sales_query = db.session.query(
            func.sum(Invoice.total).label('total'),
            func.count(Invoice.id).label('count')
        ).filter(
            Invoice.company_id == company_id,
            Invoice.type == 'I',
            extract('month', Invoice.date) == month_num,
            extract('year', Invoice.date) == previous_year
        ).first()
        
        previous_sales = float(previous_sales_query.total or 0)
        previous_invoices = int(previous_sales_query.count or 0)
        
        # Calculate growth
        growth_amount = current_sales - previous_sales
        growth_percentage = ((growth_amount / previous_sales) * 100) if previous_sales > 0 else 0
        
        # Calculate average ticket
        current_avg_ticket = (current_sales / current_invoices) if current_invoices > 0 else 0
        previous_avg_ticket = (previous_sales / previous_invoices) if previous_invoices > 0 else 0
        
        # Accumulate annual totals
        annual_current_total += current_sales
        annual_previous_total += previous_sales
        annual_current_invoices += current_invoices
        annual_previous_invoices += previous_invoices
        
        # Chart data
        chart_months.append(month_names[month_num - 1][:3])  # Abbreviated
        chart_current_sales.append(current_sales)
        chart_previous_sales.append(previous_sales)
        chart_growth_percentage.append(round(growth_percentage, 2))
        
        monthly_comparison.append({
            'month_num': month_num,
            'month_name': month_names[month_num - 1],
            'current_sales': current_sales,
            'previous_sales': previous_sales,
            'growth_amount': growth_amount,
            'growth_percentage': round(growth_percentage, 2),
            'current_invoices': current_invoices,
            'previous_invoices': previous_invoices,
            'current_avg_ticket': current_avg_ticket,
            'previous_avg_ticket': previous_avg_ticket
        })
    
    # Annual summary
    annual_growth_amount = annual_current_total - annual_previous_total
    annual_growth_percentage = ((annual_growth_amount / annual_previous_total) * 100) if annual_previous_total > 0 else 0
    
    current_avg_monthly = annual_current_total / 12
    previous_avg_monthly = annual_previous_total / 12
    
    # Find best and worst months
    months_with_sales = [m for m in monthly_comparison if m['current_sales'] > 0]
    best_month = max(months_with_sales, key=lambda x: x['current_sales']) if months_with_sales else None
    worst_month = min(months_with_sales, key=lambda x: x['current_sales']) if months_with_sales else None
    
    # Find month with highest growth
    months_with_growth = [m for m in monthly_comparison if m['previous_sales'] > 0]
    best_growth_month = max(months_with_growth, key=lambda x: x['growth_percentage']) if months_with_growth else None
    worst_growth_month = min(months_with_growth, key=lambda x: x['growth_percentage']) if months_with_growth else None
    
    annual_summary = {
        'current_year': current_year,
        'previous_year': previous_year,
        'current_total': annual_current_total,
        'previous_total': annual_previous_total,
        'growth_amount': annual_growth_amount,
        'growth_percentage': round(annual_growth_percentage, 2),
        'current_avg_monthly': current_avg_monthly,
        'previous_avg_monthly': previous_avg_monthly,
        'current_invoices': annual_current_invoices,
        'previous_invoices': annual_previous_invoices,
        'current_avg_ticket': (annual_current_total / annual_current_invoices) if annual_current_invoices > 0 else 0,
        'previous_avg_ticket': (annual_previous_total / annual_previous_invoices) if annual_previous_invoices > 0 else 0,
        'best_month': best_month,
        'worst_month': worst_month,
        'best_growth_month': best_growth_month,
        'worst_growth_month': worst_growth_month
    }
    
    # Top customers (receivers of income invoices)
    top_customers = db.session.query(
        Invoice.receiver_rfc,
        Invoice.receiver_name,
        func.sum(Invoice.total).label('total_sales'),
        func.count(Invoice.id).label('invoice_count')
    ).filter(
        Invoice.company_id == company_id,
        Invoice.type == 'I',
        extract('year', Invoice.date) == current_year
    ).group_by(
        Invoice.receiver_rfc,
        Invoice.receiver_name
    ).order_by(
        func.sum(Invoice.total).desc()
    ).limit(10).all()
    
    top_customers_data = []
    for customer in top_customers:
        total_sales = float(customer.total_sales)
        invoice_count = int(customer.invoice_count)
        avg_ticket = total_sales / invoice_count if invoice_count > 0 else 0
        percentage = (total_sales / annual_current_total * 100) if annual_current_total > 0 else 0
        
        top_customers_data.append({
            'rfc': customer.receiver_rfc,
            'name': customer.receiver_name or customer.receiver_rfc,
            'total_sales': total_sales,
            'invoice_count': invoice_count,
            'avg_ticket': avg_ticket,
            'percentage': round(percentage, 2)
        })
    
    # Chart data for JavaScript
    chart_data = {
        'months': chart_months,
        'current_sales': chart_current_sales,
        'previous_sales': chart_previous_sales,
        'growth_percentage': chart_growth_percentage
    }
    
    return render_template('sales/dashboard.html',
                         company=company,
                         available_years=available_years,
                         monthly_comparison=monthly_comparison,
                         annual_summary=annual_summary,
                         top_customers=top_customers_data,
                         chart_data=chart_data)

@invoicing_bp.route('/companies/<int:company_id>/invoices/<int:invoice_id>')
@login_required
@require_company_perm('invoices')
def invoice_detail(company_id, invoice_id):
    """Detalle completo de una factura"""
    company = Company.query.get_or_404(company_id)
    invoice = Invoice.query.get_or_404(invoice_id)
    
    if invoice.company_id != company_id:
        flash('Factura no encontrada', 'error')
        return redirect(url_for('companies.search_invoices', company_id=company_id))
        
    return render_template('invoices/detail.html', company=company, invoice=invoice)

@invoicing_bp.route('/facturacion')
@login_required
def facturacion_list():
    """Lista de empresas para acceder al módulo de facturación"""
    companies_list = current_user.accessible_companies_with_perm('facturacion')
    return render_template('facturacion/facturacion_list.html', companies=companies_list)

@invoicing_bp.route('/companies/<int:company_id>/facturacion')
@login_required
@require_company_perm('facturacion')
def facturacion_dashboard(company_id):
    """Dashboard principal de facturación"""
    company = Company.query.get_or_404(company_id)
    
    # Check if Finkok credentials are configured
    credentials = FinkokCredentials.query.filter_by(company_id=company_id).first()
    has_credentials = credentials is not None
    environment = credentials.environment if credentials else None
    
    # Get issued invoices from XML files on disk
    facturas_generadas = []
    xml_dir = os.path.join(PROJECT_ROOT, 'xml', company.rfc)
    
    if os.path.exists(xml_dir):
        try:
            from datetime import datetime as dt_util
            for filename in os.listdir(xml_dir):
                if filename.endswith('.xml'):
                    file_path = os.path.join(xml_dir, filename)
                    file_stat = os.stat(file_path)
                    
                    # Extract UUID from filename (format: SERIEFOLIO_UUID.xml)
                    uuid_val = None
                    if '_' in filename:
                        uuid_val = filename.split('_', 1)[1].replace('.xml', '')
                    
                    # Try to extract basic info from XML
                    receptor_name = ''
                    receptor_rfc = ''
                    total = 0.0
                    fecha = dt_util.fromtimestamp(file_stat.st_ctime)
                    status_sat = 'VIGENTE'
                    
                    try:
                        from lxml import etree
                        tree = etree.parse(file_path)
                        root = tree.getroot()
                        ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4'}
                        
                        total = float(root.get('Total', 0))
                        fecha_str = root.get('Fecha', '')
                        if fecha_str:
                            fecha = dt_util.fromisoformat(fecha_str)
                        
                        receptor = root.find('cfdi:Receptor', ns)
                        if receptor is not None:
                            receptor_name = receptor.get('Nombre', '')
                            receptor_rfc = receptor.get('Rfc', '')
                        
                        # Check if cancelled in DB
                        if uuid_val:
                            db_invoice = Invoice.query.filter_by(uuid=uuid_val).first()
                            if db_invoice and db_invoice.status_sat == 'CANCELADO':
                                status_sat = 'CANCELADO'
                    except Exception:
                        pass
                    
                    facturas_generadas.append({
                        'filename': filename,
                        'uuid': uuid_val,
                        'path': file_path,
                        'size': file_stat.st_size,
                        'created': fecha,
                        'receiver_name': receptor_name,
                        'receiver_rfc': receptor_rfc,
                        'total': total,
                        'status_sat': status_sat
                    })
            
            facturas_generadas.sort(key=lambda x: x['created'], reverse=True)
        except Exception as e:
            logger.error(f'Error al listar facturas emitidas: {str(e)}')
    
    return render_template('facturacion/facturacion_dashboard.html',
        company=company,
        has_credentials=has_credentials,
        environment=environment,
        invoices=facturas_generadas
    )

@invoicing_bp.route('/companies/<int:company_id>/facturacion/credenciales', methods=['GET', 'POST'])
@login_required
@require_company_perm('facturacion')
def facturacion_credenciales(company_id):
    """Configurar o actualizar credenciales de Finkok"""
    company = Company.query.get_or_404(company_id)
    credentials = FinkokCredentials.query.filter_by(company_id=company_id).first()
    
    form = FinkokCredentialsForm()
    
    if request.method == 'POST' and form.validate_on_submit():
        from utils.crypto import encrypt_password
        
        # Encrypt password
        encrypted_password = encrypt_password(form.password.data)
        
        if credentials:
            # Update existing
            credentials.username = form.username.data
            credentials.password_enc = encrypted_password
            credentials.environment = form.environment.data
            credentials.updated_at = now_mexico()
            message = 'Credenciales actualizadas correctamente'
        else:
            # Create new
            credentials = FinkokCredentials(
                company_id=company_id,
                username=form.username.data,
                password_enc=encrypted_password,
                environment=form.environment.data
            )
            db.session.add(credentials)
            message = 'Credenciales configuradas correctamente'
        
        try:
            db.session.commit()
            flash(message, 'success')
            return redirect(url_for('invoicing.facturacion_dashboard', company_id=company_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error guardando credenciales: {str(e)}')
            flash('Error al guardar credenciales', 'error')
    
    # Pre-populate form with existing credentials
    if credentials and request.method == 'GET':
        form.username.data = credentials.username
        form.environment.data = credentials.environment
    
    return render_template('facturacion/credenciales.html',
            company=company,
            form=form,
            has_credentials=credentials is not None
        )

@invoicing_bp.route('/companies/<int:company_id>/facturacion/download/<file_type>')
@login_required
@require_company_perm('facturacion')
def facturacion_download_timbrado(company_id, file_type):
    """Descargar archivo timbrado (XML o PDF)"""
    from flask import session, send_file
    
    result = session.get('timbrado_result')
    if not result or file_type not in result.get('files', {}):
        flash('Archivo no encontrado', 'error')
        return redirect(url_for('inventory.facturacion_timbrar', company_id=company_id))
    
    file_path = result['files'][file_type]
    mimetype = 'application/xml' if file_type == 'xml' else 'application/pdf'
    
    return send_file(
        file_path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"{result['uuid']}.{file_type}"
    )

@invoicing_bp.route('/companies/<int:company_id>/facturacion/pdf/<path:filename>')
@login_required
@require_company_perm('facturacion')
def facturacion_invoice_pdf(company_id, filename):
    """Genera un PDF del CFDI a partir del XML usando satcfdi, con logo de la empresa."""
    from flask import send_file, abort
    from io import BytesIO
    import base64
    import mimetypes
    from werkzeug.utils import secure_filename
    from satcfdi.cfdi import CFDI
    from satcfdi import render as cfdi_render

    company = Company.query.get_or_404(company_id)

    safe_name = secure_filename(filename)
    if not safe_name.endswith('.xml'):
        abort(404)

    xml_dir = os.path.join(PROJECT_ROOT, 'xml', company.rfc)
    xml_path = os.path.realpath(os.path.join(xml_dir, safe_name))
    if not xml_path.startswith(os.path.realpath(xml_dir) + os.sep) or not os.path.exists(xml_path):
        abort(404)

    with open(xml_path, 'rb') as f:
        xml_bytes = f.read()
    cfdi = CFDI.from_string(xml_bytes)

    html = cfdi_render.html_str(cfdi)

    logo_tag = ''
    resolved_logo = None
    if company.logo_path:
        if os.path.exists(company.logo_path):
            resolved_logo = company.logo_path
        else:
            fallback = os.path.join(PROJECT_ROOT, 'logos', os.path.basename(company.logo_path.replace('\\', '/')))
            if os.path.exists(fallback):
                resolved_logo = fallback
            else:
                logger.warning(f'Logo no encontrado para {company.rfc}: stored={company.logo_path!r} fallback={fallback!r}')
    if resolved_logo:
        try:
            with open(resolved_logo, 'rb') as lf:
                logo_b64 = base64.b64encode(lf.read()).decode('ascii')
            mime = mimetypes.guess_type(resolved_logo)[0] or 'image/png'
            logo_tag = (
                f'<div style="text-align:center;padding:8px 0;">'
                f'<img src="data:{mime};base64,{logo_b64}" '
                f'style="max-height:90px;max-width:280px;"/>'
                f'</div>'
            )
        except Exception as e:
            logger.warning(f'No se pudo incrustar logo para {company.rfc}: {e}')

    if logo_tag:
        if '<body>' in html:
            html = html.replace('<body>', '<body>' + logo_tag, 1)
        else:
            html = logo_tag + html

    import weasyprint
    pdf_bytes = weasyprint.HTML(string=html).write_pdf(stylesheets=[cfdi_render.PDF_CSS])

    uuid_val = None
    if '_' in safe_name:
        uuid_val = safe_name.split('_', 1)[1].replace('.xml', '')
    download_name = f"{uuid_val or safe_name.replace('.xml', '')}.pdf"

    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=download_name
    )

@invoicing_bp.route('/companies/<int:company_id>/facturacion/estado', methods=['GET', 'POST'])
@login_required
@require_company_perm('facturacion')
def facturacion_estado(company_id):
    """Consultar estado de CFDI"""
    import os
    from datetime import datetime

    company = Company.query.get_or_404(company_id)
    form = ConsultarEstadoForm()
    
    # Listar facturas generadas por el sistema
    facturas_generadas = []
    xml_dir = os.path.join(PROJECT_ROOT, 'xml', company.rfc)
    
    if os.path.exists(xml_dir):
        try:
            for filename in os.listdir(xml_dir):
                if filename.endswith('.xml'):
                    file_path = os.path.join(xml_dir, filename)
                    file_stat = os.stat(file_path)
                    
                    # Extraer UUID del nombre del archivo (formato: SERIEFOLIO_UUID.xml)
                    uuid = None
                    if '_' in filename:
                        uuid = filename.split('_')[1].replace('.xml', '')
                    
                    facturas_generadas.append({
                        'filename': filename,
                        'uuid': uuid,
                        'path': file_path,
                        'size': file_stat.st_size,
                        'created': datetime.fromtimestamp(file_stat.st_ctime)
                    })
            
            # Ordenar por fecha de creación (más recientes primero)
            facturas_generadas.sort(key=lambda x: x['created'], reverse=True)
        except Exception as e:
            logger.error(f'Error al listar facturas: {str(e)}')
    
    # Consultar estado (cuando se envía el form o se hace clic en "Checar Status")
    result = None
    if request.method == 'POST':
        # Verificar si es consulta de factura generada
        xml_filepath = request.form.get('xml_filepath')
        
        if xml_filepath and os.path.exists(xml_filepath):
            try:
                from services.facturacion_service import FacturacionService
                
                with open(xml_filepath, 'r', encoding='utf-8') as f:
                    xml_content = f.read()
                
                service = FacturacionService()
                result = service.consultar_estado(cfdi_xml=xml_content)
                
                if not result['success']:
                    flash(f'Error al consultar: {result["message"]}', 'error')
                    
            except Exception as e:
                logger.error(f'Error al consultar estado: {str(e)}')
                flash(f'Error: {str(e)}', 'error')
        
        # Consulta manual (formulario tradicional)
        elif form.validate_on_submit():
            try:
                from services.facturacion_service import FacturacionService
                
                service = FacturacionService()
                
                if form.xml_file.data:
                    xml_content = form.xml_file.data.read().decode('utf-8')
                    result = service.consultar_estado(cfdi_xml=xml_content)
                elif form.uuid.data:
                    if not all([form.rfc_emisor.data, form.rfc_receptor.data, form.total.data]):
                        flash('Para consultar por UUID, debe proporcionar RFC emisor, RFC receptor y total', 'warning')
                    else:
                        result = service.consultar_estado(
                            uuid=form.uuid.data,
                            rfc_emisor=form.rfc_emisor.data,
                            rfc_receptor=form.rfc_receptor.data,
                            total=str(form.total.data)
                        )
                
                if result and not result['success']:
                    flash(f'Error al consultar: {result["message"]}', 'error')
                    
            except Exception as e:
                logger.error(f'Error al consultar estado: {str(e)}')
                flash(f'Error: {str(e)}', 'error')
    
    return render_template('facturacion/estado.html',
        company=company,
        form=form,
        result=result,
        facturas_generadas=facturas_generadas
    )

@invoicing_bp.route('/companies/<int:company_id>/facturacion/lista69b', methods=['GET', 'POST'])
@login_required
@require_company_perm('facturacion')
def facturacion_lista69b(company_id):
    """Verificar RFC en lista 69B"""
    company = Company.query.get_or_404(company_id)
    form = Lista69BForm()
    
    if request.method == 'POST' and form.validate_on_submit():
        try:
            from services.facturacion_service import FacturacionService
            
            service = FacturacionService()  # No requiere credenciales
            result = service.verificar_lista_69b(form.rfc.data)
            
            if result['success']:
                return render_template('facturacion/lista69b.html',
                    company=company,
                    form=form,
                    result=result
                )
            else:
                flash(f'Error al consultar: {result["message"]}', 'error')
                
        except Exception as e:
            logger.error(f'Error en consulta lista 69B: {str(e)}')
            flash(f'Error al verificar RFC: {str(e)}', 'error')
    
    return render_template('facturacion/lista69b.html',
        company=company,
        form=form
    )

@invoicing_bp.route('/companies/<int:company_id>/facturacion/actualizar_estado/<string:uuid>', methods=['POST'])
@login_required
@require_company_perm('facturacion')
def facturacion_actualizar_estado_db(company_id, uuid):
    """Actualiza el estado de una factura específica consultando al SAT."""
    company = Company.query.get_or_404(company_id)
    if not current_user.can_access_company(company_id):
        flash('No tienes acceso a esta empresa', 'error')
        return redirect(url_for('main.index'))
        
    invoice = Invoice.query.filter_by(company_id=company.id, uuid=uuid).first()
    xml_content = invoice.xml_content if invoice and invoice.xml_content else None
    created_from_xml = False

    if not xml_content:
        xml_path = find_company_invoice_xml_path(company.rfc, uuid)
        if xml_path:
            with open(xml_path, 'r', encoding='utf-8') as f:
                xml_content = f.read()

    if not invoice and xml_content:
        try:
            invoice_data = parse_invoice_xml_for_db(xml_content, fallback_uuid=uuid)
            invoice = Invoice(company_id=company.id, status_sat='VIGENTE', **invoice_data)
            db.session.add(invoice)
            db.session.flush()
            created_from_xml = True
        except Exception as e:
            logger.warning(f"No se pudo registrar la factura {uuid} desde XML: {str(e)}")

    if not invoice and not xml_content:
        flash('No se encontrÃ³ la factura en la base de datos ni el XML emitido para consultar su estado.', 'warning')
        return redirect(url_for('invoicing.facturacion_dashboard', company_id=company.id))
    
    try:
        from services.facturacion_service import FacturacionService
        service = FacturacionService()
        
        # Use the XML to check status if available
        result = None
        if xml_content:
            result = service.consultar_estado(cfdi_xml=xml_content)
        elif invoice and invoice.issuer_rfc and invoice.receiver_rfc and invoice.total is not None:
            result = service.consultar_estado(
                uuid=uuid,
                rfc_emisor=invoice.issuer_rfc,
                rfc_receptor=invoice.receiver_rfc,
                total=str(invoice.total)
            )
        else:
            flash('No hay suficientes datos (XML o RFCs/Total) para consultar al SAT.', 'warning')
            return redirect(url_for('invoicing.facturacion_dashboard', company_id=company.id))
            
        if result and result['success']:
            estado = result.get('estado', '').upper()
            if estado == 'CANCELADO':
                if invoice:
                    invoice.status_sat = 'CANCELADO'
                    db.session.commit()
                flash(f'El SAT confirmó que la factura {uuid[:8]} está CANCELADA.', 'success')
            elif estado == 'VIGENTE':
                # Si estaba en proceso de cancelación pero el SAT dice vigente, puede que haya sido rechazada o siga en proceso
                # El SAT también devuelve un campo EstatusCancelacion si se solicita
                if invoice:
                    invoice.status_sat = 'VIGENTE'
                    db.session.commit()
                flash(f'El SAT indica que la factura {uuid[:8]} sigue VIGENTE.', 'info')
            else:
                if created_from_xml:
                    db.session.commit()
                flash(f'Estado devuelto por el SAT: {estado}', 'info')
        else:
            if created_from_xml:
                db.session.commit()
            flash(f'Error al consultar el SAT: {result.get("message", "Error desconocido")}', 'error')
            
    except Exception as e:
        if created_from_xml:
            db.session.rollback()
        logger.error(f"Error actualizando estado de {uuid}: {str(e)}")
        flash(f'Error al conectar con el SAT: {str(e)}', 'error')
        
    return redirect(url_for('invoicing.facturacion_dashboard', company_id=company.id))

@invoicing_bp.route('/companies/<int:company_id>/facturacion/crear', methods=['GET', 'POST'])
@login_required
@require_company_perm('facturacion')
def crear_factura(company_id):
    """Generador de CFDI - Crear, generar XML y timbrar automáticamente"""
    company = Company.query.get_or_404(company_id)
    
    # Verificar que tenga credenciales Finkok
    credentials = FinkokCredentials.query.filter_by(company_id=company_id).first()
    if not credentials:
        flash('Debe configurar las credenciales de Finkok primero', 'warning')
        return redirect(url_for('invoicing.facturacion_credenciales', company_id=company_id))
    
    # Crear formularios
    form_comprobante = CFDIComprobanteForm()
    form_receptor = CFDIReceptorForm()
    
    # Si es POST, procesamos
    if request.method == 'POST':
        return generar_y_timbrar_cfdi(company, credentials, form_comprobante, form_receptor)
    
    # GET: Obtener serie y folio actual
    # Si el usuario especifica una serie en la URL, usarla; sino, usar "A" por defecto
    serie_param = request.args.get('serie', 'A')

    # Buscar el contador para esta serie
    folio_counter = InvoiceFolioCounter.query.filter_by(
        company_id=company_id,
        serie=serie_param
    ).first()

    if not folio_counter:
        # Crear contador nuevo para esta serie
        folio_counter = InvoiceFolioCounter(
            company_id=company_id,
            serie=serie_param,
            current_folio=0
        )
        db.session.add(folio_counter)
        db.session.commit()

    # El siguiente folio es el actual + 1
    next_folio = folio_counter.current_folio + 1

    # Pre-poblar el formulario con serie y folio
    form_comprobante.serie.data = serie_param
    form_comprobante.folio.data = str(next_folio).zfill(7)  # Formato: 0000001

    # Pre-llenar lugar de expedición con CP de la empresa
    if company.postal_code:
        form_comprobante.lugar_expedicion.data = company.postal_code

    # Cargar plantilla si se proporciona template_id
    template_items = []
    selected_template = None
    template_id = request.args.get('template_id')
    if template_id:
        selected_template = InvoiceTemplate.query.filter_by(
            id=template_id,
            company_id=company_id,
            active=True
        ).first()
        if selected_template:
            for item in selected_template.items:
                template_items.append({
                    'type': item.item_type,
                    'name': item.item_name,
                    'quantity': item.quantity,
                    'price': item.item_price,
                    'product_id': item.product_id,
                    'service_id': item.service_id
                })

    # Cargar lista de plantillas disponibles
    available_templates = InvoiceTemplate.query.filter_by(
        company_id=company_id,
        active=True
    ).order_by(InvoiceTemplate.name).all()

    return render_template('facturacion/crear_factura.html',
        company=company,
        form_comprobante=form_comprobante,
        form_receptor=form_receptor,
        available_templates=available_templates,
        selected_template=selected_template,
        template_items=template_items
    )

@invoicing_bp.route('/companies/<int:company_id>/facturacion/cancelar/<string:uuid>', methods=['GET', 'POST'])
@login_required
@require_company_perm('facturacion')
def facturacion_cancelar(company_id, uuid):
    company = Company.query.get_or_404(company_id)
    if not current_user.can_access_company(company_id):
        flash('No tienes acceso a esta empresa', 'error')
        return redirect(url_for('main.index'))
        
    perms = current_user.get_company_permissions(company_id)
    if not perms.get('facturacion'):
        flash('No tienes permiso para facturación', 'error')
        return redirect(url_for('inventory.dashboard', company_id=company_id))

    invoice = Invoice.query.filter_by(company_id=company.id, uuid=uuid).first_or_404()
    
    # We need the credentials environment
    credentials = FinkokCredentials.query.filter_by(company_id=company.id, active=True).first()
    if not credentials:
        flash('Credenciales de Finkok no configuradas.', 'error')
        return redirect(url_for('invoicing.facturacion_dashboard', company_id=company.id))

    form = CancelarFacturaForm()
    if form.validate_on_submit():
        try:
            from services.facturacion_service import FacturacionService
            from utils.crypto import decrypt_password
            from satcfdi.models import Signer
            
            fiel_cer_file = form.fiel_cer.data
            fiel_key_file = form.fiel_key.data
            fiel_password = form.fiel_password.data
            motivo = form.motivo.data
            sustitucion_uuid = form.sustitucion_uuid.data if form.sustitucion_uuid.data else None

            # Leer archivos en memoria directamente
            cer_bytes = fiel_cer_file.read()
            key_bytes = fiel_key_file.read()

            try:
                signer = Signer.load(cer_bytes, key_bytes, fiel_password)
                password = decrypt_password(credentials.password_enc)
                
                facturacion_service = FacturacionService(
                    finkok_username=credentials.username,
                    finkok_password=password,
                    environment=credentials.environment,
                    signer=signer
                )
                
                # Llamar a cancelar
                result = facturacion_service.cancelar_factura(
                    cfdi_xml=invoice.xml_content,
                    reason=motivo,
                    substitution_uuid=sustitucion_uuid
                )
                
                if result['success']:
                    # Guardar el acuse de cancelación
                    if 'acuse' in result and result['acuse']:
                        xml_dir = os.path.join(PROJECT_ROOT, 'xml', company.rfc)
                        os.makedirs(xml_dir, exist_ok=True)
                        acuse_path = os.path.join(xml_dir, f"acuse_cancelacion_{uuid}.xml")
                        with open(acuse_path, 'w', encoding='utf-8') as f:
                            f.write(result['acuse'])
                        logger.info(f"Acuse de cancelación guardado en {acuse_path}")
                    
                    # Marcar en proceso, ya que requiere consultar el estado después
                    invoice.status_sat = 'EN_PROCESO_CANCELACION'
                    db.session.commit()
                    flash('Solicitud de cancelación enviada al SAT. El estado se actualizará a EN_PROCESO_CANCELACION. Consulte el estado más tarde.', 'success')
                    return redirect(url_for('invoicing.facturacion_dashboard', company_id=company.id))
                else:
                    error_msg = result.get('message', '').lower()
                    if 'timeout' in error_msg or 'time out' in error_msg:
                        invoice.status_sat = 'VERIFICACION_PENDIENTE'
                        db.session.commit()
                        flash('La solicitud tardó mucho en responder (Timeout). Se marcó como VERIFICACION_PENDIENTE. Por favor consulte el estado más tarde.', 'warning')
                        return redirect(url_for('invoicing.facturacion_dashboard', company_id=company.id))
                    else:
                        flash(f'Error al cancelar factura: {result["message"]}', 'error')

            except ValueError as ve:
                # Error al cargar la FIEL por contraseña incorrecta
                flash(f'Error con los archivos FIEL o contraseña: {str(ve)}', 'error')
                
        except Exception as e:
            logger.error(f'Error cancelando factura: {str(e)}')
            flash(f'Error inesperado: {str(e)}', 'error')

    return render_template('facturacion/cancelar_factura.html', company=company, form=form, invoice=invoice)

