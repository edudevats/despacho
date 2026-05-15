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


companies_bp = Blueprint('companies', __name__)

@companies_bp.route('/companies')
@login_required
def companies():
    if current_user.is_admin:
        companies_list = Company.query.order_by(Company.name).all()
    else:
        companies_list = current_user.get_accessible_companies()
    return render_template('companies.html', companies=companies_list)

@companies_bp.route('/companies/add', methods=['POST'])
@login_required
def add_company():
    rfc = request.form['rfc']
    name = request.form['name']
    postal_code = request.form.get('postal_code')
    logo = request.files.get('logo')
    
    logo_path = None
    if logo and logo.filename:
        # Validar extensión
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        if '.' in logo.filename:
            ext = logo.filename.rsplit('.', 1)[1].lower()
            if ext in allowed_extensions:
                # Crear carpeta logos si no existe
                logos_dir = os.path.join(os.path.dirname(__file__), 'logos')
                os.makedirs(logos_dir, exist_ok=True)
                
                # Guardar con nombre único (RFC)
                filename = f"{rfc}.{ext}"
                logo_path = os.path.join(logos_dir, filename)
                logo.save(logo_path)
    
    new_company = Company(
        rfc=rfc, 
        name=name,
        postal_code=postal_code,
        logo_path=logo_path
    )
    db.session.add(new_company)
    db.session.commit()
    
    return redirect(url_for('companies.companies'))

@companies_bp.route('/companies/delete/<int:company_id>', methods=['POST'])
@login_required
def delete_company(company_id):
    company = Company.query.get_or_404(company_id)
    
    try:
        # Delete dependencies in order to respect FK constraints
        
        # 1. Delete Movements (referencing Invoice, Category, Company)
        Movement.query.filter_by(company_id=company.id).delete()
        
        # 2. Delete Invoices (referencing Supplier, Company)
        Invoice.query.filter_by(company_id=company.id).delete()
        
        # 3. Delete Suppliers (referencing Company)
        Supplier.query.filter_by(company_id=company.id).delete()
        
        # 4. Delete Categories (referencing Company)
        Category.query.filter_by(company_id=company.id).delete()

        # 5. Delete Inventory (Product referencing Company, Transaction referencing Product)
        # Need to find products first to delete transactions
        products = Product.query.filter_by(company_id=company.id).all()
        for p in products:
            InventoryTransaction.query.filter_by(product_id=p.id).delete()
        Product.query.filter_by(company_id=company.id).delete()
        
        # 6. Delete TaxPayments (referencing Company)
        TaxPayment.query.filter_by(company_id=company.id).delete()
        
        # 7. Delete Company
        db.session.delete(company)
        
        db.session.commit()
        flash('Empresa y todos sus datos eliminados correctamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar empresa: {str(e)}', 'error')
        
    return redirect(url_for('companies.companies'))

@companies_bp.route('/companies/edit/<int:company_id>', methods=['GET', 'POST'])
@login_required
def edit_company(company_id):
    company = Company.query.get_or_404(company_id)
    
    if request.method == 'POST':
        company.rfc = request.form['rfc']
        company.name = request.form['name']
        company.postal_code = request.form.get('postal_code')
        
        # Manejar logo
        logo = request.files.get('logo')
        if logo and logo.filename:
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            if '.' in logo.filename:
                ext = logo.filename.rsplit('.', 1)[1].lower()
                if ext in allowed_extensions:
                    logos_dir = os.path.join(os.path.dirname(__file__), 'logos')
                    os.makedirs(logos_dir, exist_ok=True)
                    
                    # Eliminar logo anterior si existe
                    if company.logo_path and os.path.exists(company.logo_path):
                        try:
                            os.remove(company.logo_path)
                        except:
                            pass
                    
                    filename = f"{company.rfc}.{ext}"
                    logo_path = os.path.join(logos_dir, filename)
                    logo.save(logo_path)
                    company.logo_path = logo_path
        
        try:
            db.session.commit()
            flash('Empresa actualizada correctamente.', 'success')
            return redirect(url_for('companies.companies'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar empresa: {str(e)}', 'error')
            
    return render_template('edit_company.html', company=company)

@companies_bp.route('/companies/sync/<int:company_id>', methods=['GET', 'POST'])
@login_required
@require_company_perm('sync')
def sync_company(company_id):
    company = Company.query.get_or_404(company_id)
    
    if request.method == 'GET':
        from datetime import datetime, timedelta
        
        # Get last invoice date
        last_invoice_date = db.session.query(db.func.max(Invoice.date)).filter_by(company_id=company.id).scalar()
        
        if last_invoice_date:
            # Start from the last invoice date to ensure we catch any late arrivals for that day
            start_date = last_invoice_date.strftime('%Y-%m-%d')
        else:
            # Default to 30 days ago
            start_date = (now_mexico() - timedelta(days=30)).strftime('%Y-%m-%d')
            
        end_date = now_mexico().strftime('%Y-%m-%d')
        
        return render_template('sync.html', company=company, start_date=start_date, end_date=end_date)
    
    if request.method == 'POST':
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        
        # Enforce FIEL usage
        fiel_password = request.form['fiel_password']
        fiel_cer = request.files['fiel_cer']
        fiel_key = request.files['fiel_key']

        # Save temporary files
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.cer') as tmp_cer:
            fiel_cer.save(tmp_cer.name)
            cer_path = tmp_cer.name

        with tempfile.NamedTemporaryFile(delete=False, suffix='.key') as tmp_key:
            fiel_key.save(tmp_key.name)
            key_path = tmp_key.name

        sat_service = SATService(
            rfc=company.rfc,
            fiel_cer=cer_path,
            fiel_key=key_path,
            fiel_password=fiel_password
        )

    try:
        from datetime import datetime
        import re
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        
        # Download both Received and Emitted invoices
        received_invoices = sat_service.download_received_invoices(start_date, end_date)
        emitted_invoices = sat_service.download_emitted_invoices(start_date, end_date)
        
        all_invoices = received_invoices + emitted_invoices
        
        # Create folder structure for saving invoices
        # Sanitize company name for use in folder names
        safe_company_name = re.sub(r'[<>:"/\\|?*]', '_', company.name)
        invoices_folder = os.path.join(os.path.dirname(__file__), 'facturas', safe_company_name)
        os.makedirs(invoices_folder, exist_ok=True)
        
        # Process invoices
        count = 0
        updated_count = 0
        modified_details = []
        files_saved = 0
        
        for inv_data in all_invoices:
            # Save XML to file first (always save/overwrite to ensure latest version)
            xml_filename = f"{inv_data['uuid']}.xml"
            xml_filepath = os.path.join(invoices_folder, xml_filename)
            
            # Always write the file to ensure we have the exact version from SAT
            with open(xml_filepath, 'w', encoding='utf-8') as xml_file:
                xml_file.write(inv_data['xml'])
            files_saved += 1
            
            # Check if exists in database
            existing_inv = Invoice.query.filter_by(uuid=inv_data['uuid']).first()
            
            if existing_inv:
                # Check for changes in existing invoice
                changes = []
                
                # --- Comprobante Changes ---
                if abs(existing_inv.total - inv_data['total']) > 0.01:
                    changes.append(f"Comprobante: Total ({existing_inv.total} -> {inv_data['total']})")
                
                # Check string fields (handling None)
                if (existing_inv.serie or '') != (inv_data.get('serie') or ''):
                    changes.append(f"Comprobante: Serie ({existing_inv.serie} -> {inv_data.get('serie')})")
                if (existing_inv.folio or '') != (inv_data.get('folio') or ''):
                    changes.append(f"Comprobante: Folio ({existing_inv.folio} -> {inv_data.get('folio')})")
                    
                # --- Emisor Changes ---
                # Name is often slightly different in encoding, maybe skip strict check or normalize?
                # We will check strict for now as requested
                if (existing_inv.issuer_name or '') != (inv_data.get('issuer_name') or ''):
                    changes.append(f"Emisor: Nombre")
                if (existing_inv.regimen_fiscal_emisor or '') != (inv_data.get('regimen_fiscal_emisor') or ''):
                     changes.append(f"Emisor: Régimen Fiscal")

                # --- Receptor Changes ---
                if (existing_inv.receiver_name or '') != (inv_data.get('receiver_name') or ''):
                    changes.append(f"Receptor: Nombre")
                if (existing_inv.domicilio_fiscal_receptor or '') != (inv_data.get('domicilio_fiscal_receptor') or ''):
                     changes.append(f"Receptor: Domicilio")
                if (existing_inv.regimen_fiscal_receptor or '') != (inv_data.get('regimen_fiscal_receptor') or ''):
                     changes.append(f"Receptor: Régimen Fiscal")

                # --- Timbre (SAT) Changes ---
                # Check if 'fecha_timbrado' matches (aware of timezone offset issues in naive comparison, but typically exact match expected)
                # We compare string ISO format if strictly needed, or datetime objects
                # If existing is None, it's an update, not a "change" in strict sense but good to note
                if existing_inv.fecha_timbrado != inv_data.get('fecha_timbrado'):
                     changes.append(f"Timbre: Fecha Timbrado")
                
                if changes:
                    # Update the record
                    existing_inv.xml_content = inv_data['xml']
                    existing_inv.total = inv_data['total']
                    existing_inv.subtotal = inv_data['subtotal']
                    existing_inv.tax = inv_data['tax']
                    existing_inv.issuer_name = inv_data.get('issuer_name')
                    existing_inv.receiver_name = inv_data.get('receiver_name')
                    existing_inv.serie = inv_data.get('serie')
                    existing_inv.folio = inv_data.get('folio')
                    existing_inv.lugar_expedicion = inv_data.get('lugar_expedicion')
                    existing_inv.no_certificado = inv_data.get('no_certificado')
                    existing_inv.sello = inv_data.get('sello')
                    existing_inv.certificado = inv_data.get('certificado')
                    existing_inv.regimen_fiscal_emisor = inv_data.get('regimen_fiscal_emisor')
                    existing_inv.regimen_fiscal_receptor = inv_data.get('regimen_fiscal_receptor')
                    existing_inv.domicilio_fiscal_receptor = inv_data.get('domicilio_fiscal_receptor')
                    existing_inv.fecha_timbrado = inv_data.get('fecha_timbrado')
                    existing_inv.rfc_prov_certif = inv_data.get('rfc_prov_certif')
                    existing_inv.sello_sat = inv_data.get('sello_sat')
                    existing_inv.no_certificado_sat = inv_data.get('no_certificado_sat')
                    # Also update version/payment terms if needed
                    existing_inv.version = inv_data.get('version')
                    existing_inv.payment_terms = inv_data.get('payment_terms')
                    
                    updated_count += 1
                    modified_details.append(f"Factura {inv_data['uuid']} ({inv_data['date'].strftime('%Y-%m-%d') if inv_data['date'] else '?'}): {', '.join(changes)}")

            else:
                # Create NEW Invoice
                # Determine Movement Type
                is_emitted = (inv_data['issuer_rfc'] == company.rfc)
                mov_type = 'INCOME' if is_emitted else 'EXPENSE'
                
                # For received invoices (expenses), create/update supplier
                supplier_id = None
                if not is_emitted:
                    supplier = get_or_create_supplier(
                        company_id=company.id,
                        rfc=inv_data['issuer_rfc'],
                        business_name=inv_data.get('issuer_name')
                    )
                    supplier_id = supplier.id
                
                new_inv = Invoice(
                    uuid=inv_data['uuid'],
                    company_id=company.id,
                    supplier_id=supplier_id,
                    date=inv_data['date'],
                    total=inv_data['total'],
                    subtotal=inv_data['subtotal'],
                    tax=inv_data['tax'],
                    type=inv_data['type'],
                    issuer_rfc=inv_data['issuer_rfc'],
                    issuer_name=inv_data.get('issuer_name'),
                    receiver_rfc=inv_data['receiver_rfc'],
                    receiver_name=inv_data.get('receiver_name'),
                    forma_pago=inv_data.get('forma_pago'),
                    metodo_pago=inv_data.get('metodo_pago'),
                    uso_cfdi=inv_data.get('uso_cfdi'),
                    descripcion=inv_data.get('descripcion'),
                    xml_content=inv_data['xml'],
                    # Standard fields
                    periodicity=inv_data.get('periodicity'),
                    months=inv_data.get('months'),
                    fiscal_year=inv_data.get('fiscal_year'),
                    payment_terms=inv_data.get('payment_terms'),
                    currency=inv_data.get('currency'),
                    exchange_rate=inv_data.get('exchange_rate'),
                    exportation=inv_data.get('exportation'),
                    version=inv_data.get('version'),
                    # --- New Fields for Granular Tracking ---
                    # Comprobante
                    serie=inv_data.get('serie'),
                    folio=inv_data.get('folio'),
                    lugar_expedicion=inv_data.get('lugar_expedicion'),
                    no_certificado=inv_data.get('no_certificado'),
                    sello=inv_data.get('sello'),
                    certificado=inv_data.get('certificado'),
                    # Emisor
                    regimen_fiscal_emisor=inv_data.get('regimen_fiscal_emisor'),
                    # Receptor
                    regimen_fiscal_receptor=inv_data.get('regimen_fiscal_receptor'),
                    domicilio_fiscal_receptor=inv_data.get('domicilio_fiscal_receptor'),
                    # Timbre
                    fecha_timbrado=inv_data.get('fecha_timbrado'),
                    rfc_prov_certif=inv_data.get('rfc_prov_certif'),
                    sello_sat=inv_data.get('sello_sat'),
                    no_certificado_sat=inv_data.get('no_certificado_sat')
                )
                db.session.add(new_inv)
                
                if supplier_id:
                    update_supplier_stats(supplier_id)
                
                # Movement creation logic
                metodo_pago = inv_data.get('metodo_pago', 'PUE')
                if metodo_pago != 'PPD':
                    new_mov = Movement(
                        invoice=new_inv,
                        company_id=company.id,
                        amount=inv_data['total'],
                        type=mov_type,
                        description=f"Factura {inv_data['issuer_rfc'] if not is_emitted else inv_data['receiver_rfc']}",
                        date=inv_data['date']
                    )
                    db.session.add(new_mov)
                count += 1
        
        db.session.commit()
        
        # Construct summary message
        messages = []
        if count > 0:
            messages.append(f"{count} facturas nuevas importadas.")
        if updated_count > 0:
            messages.append(f"{updated_count} facturas existentes actualizadas.")
        
        if modified_details:
            # Show first 5 details if many
            details_text = "<br>".join(modified_details[:5])
            if len(modified_details) > 5:
                details_text += f"<br>... y {len(modified_details)-5} más."
            flash(f"Sincronización finalizada.<br>{' '.join(messages)}<br><strong>Cambios detectados:</strong><br>{details_text}", 'warning' if updated_count > 0 else 'success')
        elif count > 0:
            flash(f"Sincronización completada. {count} facturas nuevas.", 'success')
        else:
            flash("Sincronización al día. No se encontraron cambios ni facturas nuevas.", 'success')
        
    except SATError as sat_e:
        import traceback
        traceback.print_exc()
        # SATError contains detailed user-friendly messages with suggested actions
        user_message = sat_e.get_user_message()
        logger.error(f'SAT error for company {company.rfc}: Code={sat_e.code}, Message={sat_e.mensaje}, Raw={sat_e.raw_message}')
        flash(user_message, 'error')
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Translate technical errors to user-friendly messages
        error_str = str(e).lower()
        if 'invalid fiel' in error_str or 'password' in error_str or 'decrypt' in error_str:
            user_message = 'La contraseña FIEL es incorrecta o los archivos no son válidos.'
        elif 'certificado' in error_str or 'certificate' in error_str or 'expired' in error_str:
            user_message = 'El certificado FIEL está expirado o no es válido.'
        elif 'timeout' in error_str or 'connection' in error_str:
            user_message = 'No se pudo conectar con el SAT. Por favor intente más tarde.'
        elif 'binding parameter' in error_str or 'programming' in error_str:
            user_message = 'Hubo un problema procesando las facturas. Por favor contacte soporte técnico.'
        else:
            user_message = 'Ocurrió un error durante la sincronización. Por favor intente nuevamente.'
        
        # Log technical error for debugging
        logger.error(f'Sync error for company {company.rfc}: {str(e)}')
        flash(user_message, 'error')
    finally:
        # Cleanup temp files
        if 'cer_path' in locals() and os.path.exists(cer_path):
            os.remove(cer_path)
        if 'key_path' in locals() and os.path.exists(key_path):
            os.remove(key_path)
        
    return redirect(url_for('companies.companies'))

@companies_bp.route('/companies/<int:company_id>/search')
@login_required
@require_company_perm('invoices')
def search_invoices(company_id):
    """Búsqueda avanzada de facturas"""
    company = Company.query.get_or_404(company_id)
    
    # Parámetros de búsqueda
    supplier_id = request.args.get('supplier_id', type=int)
    category_id = request.args.get('category_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    min_amount = request.args.get('min_amount', type=float)
    max_amount = request.args.get('max_amount', type=float)
    search_text = request.args.get('q', '')
    
    # Query base
    query = Invoice.query.filter_by(company_id=company_id)
    
    # Aplicar filtros
    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)
    
    if date_from:
        query = query.filter(Invoice.date >= datetime.fromisoformat(date_from))
    
    if date_to:
        query = query.filter(Invoice.date <= datetime.fromisoformat(date_to))
    
    if min_amount:
        query = query.filter(Invoice.total >= min_amount)
    
    if max_amount:
        query = query.filter(Invoice.total <= max_amount)
    
    if search_text:
        query = query.filter(
            db.or_(
                Invoice.descripcion.ilike(f'%{search_text}%'),
                Invoice.issuer_name.ilike(f'%{search_text}%'),
                Invoice.receiver_name.ilike(f'%{search_text}%')
            )
        )
    
    # Ordenar y paginar
    invoices = query.order_by(Invoice.date.desc()).all()
    
    # Listas para filtros
    suppliers_list = Supplier.query.filter_by(company_id=company_id, active=True).order_by(Supplier.business_name).all()
    categories_list = Category.query.filter_by(company_id=company_id, active=True).all()
    
    return render_template('search/invoices.html',
        company=company,
        invoices=invoices,
        suppliers=suppliers_list,
        categories=categories_list,
        filters={
            'supplier_id': supplier_id,
            'category_id': category_id,
            'date_from': date_from,
            'date_to': date_to,
            'min_amount': min_amount,
            'max_amount': max_amount,
            'q': search_text
        }
    )

@companies_bp.route('/companies/<int:company_id>/qr')
@login_required
@require_company_perm('invoices', 'facturacion')
def company_qr(company_id):
    """Generate QR code for company"""
    company = Company.query.get_or_404(company_id)
    qr_base64 = QRService.generate_company_qr(company)
    return render_template('qr_display.html', 
        company=company, 
        qr_image=qr_base64,
        title=f'QR - {company.name}'
    )

@companies_bp.route('/companies/<int:company_id>/qr/download')
@login_required
@require_company_perm('invoices', 'facturacion')
def company_qr_download(company_id):
    """Download QR code as PNG"""
    company = Company.query.get_or_404(company_id)
    data = f"RFC: {company.rfc}\nNombre: {company.name}"
    qr_bytes = QRService.generate_qr_bytes(data)
    
    return Response(
        qr_bytes,
        mimetype='image/png',
        headers={'Content-Disposition': f'attachment; filename=qr_{company.rfc}.png'}
    )

@companies_bp.route('/companies/<int:company_id>/invoices/<int:invoice_id>/qr')
@login_required
@require_company_perm('invoices', 'facturacion')
def invoice_qr(company_id, invoice_id):
    """Generate SAT verification QR for invoice"""
    invoice = Invoice.query.get_or_404(invoice_id)
    
    if invoice.company_id != company_id:
        flash('Factura no encontrada', 'error')
        return redirect(url_for('companies.search_invoices', company_id=company_id))
    
    # Get seal last 8 chars from XML if available
    seal_last_8 = "00000000"
    if invoice.xml_content:
        import re
        match = re.search(r'Sello="([^"]+)"', invoice.xml_content)
        if match:
            seal_last_8 = match.group(1)[-8:]
    
    qr_base64 = QRService.generate_cfdi_qr(
        uuid=invoice.uuid,
        issuer_rfc=invoice.issuer_rfc,
        receiver_rfc=invoice.receiver_rfc,
        total=invoice.total,
        seal_last_8=seal_last_8
    )
    
    return render_template('qr_display.html',
        invoice=invoice,
        qr_image=qr_base64,
        title=f'QR CFDI - {invoice.uuid}'
    )

@companies_bp.route('/api/companies/<int:company_id>/stats')
@login_required
@cache.cached(timeout=60, query_string=True)
def api_company_stats(company_id):
    """API endpoint para estadísticas en tiempo real (cached 60s)"""
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
        'income': float(income),
        'expense': float(expense),
        'balance': float(income - expense),
        'month': month,
        'year': year
    })

