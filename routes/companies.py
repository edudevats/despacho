"""
Company management routes - CRUD operations and sync.
"""

import os
import re
import logging
import tempfile
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from extensions import db
from models import Company, Invoice, Movement, Category, Supplier
from services.sat_service import SATService, SATError

logger = logging.getLogger(__name__)

companies_bp = Blueprint('companies', __name__, url_prefix='/companies')


@companies_bp.route('/')
@login_required
def list_companies():
    """List all companies."""
    companies_list = Company.query.all()
    return render_template('companies.html', companies=companies_list)


@companies_bp.route('/add', methods=['POST'])
@login_required
def add_company():
    """Add a new company."""
    rfc = request.form.get('rfc', '').strip().upper()
    name = request.form.get('name', '').strip()
    
    if not rfc or not name:
        flash('RFC y Nombre son requeridos.', 'error')
        return redirect(url_for('companies.list_companies'))
    
    # Check for duplicate RFC
    if Company.query.filter_by(rfc=rfc).first():
        flash(f'Ya existe una empresa con el RFC {rfc}.', 'error')
        return redirect(url_for('companies.list_companies'))
    
    new_company = Company(rfc=rfc, name=name)
    db.session.add(new_company)
    db.session.commit()
    
    logger.info(f"Company created: {name} ({rfc})")
    flash(f'Empresa "{name}" creada correctamente.', 'success')
    return redirect(url_for('companies.list_companies'))


@companies_bp.route('/delete/<int:company_id>', methods=['POST'])
@login_required
def delete_company(company_id):
    """Delete a company and all related data."""
    company = Company.query.get_or_404(company_id)
    company_name = company.name
    
    try:
        # Delete dependencies in order to respect FK constraints
        Movement.query.filter_by(company_id=company.id).delete()
        Invoice.query.filter_by(company_id=company.id).delete()
        Supplier.query.filter_by(company_id=company.id).delete()
        Category.query.filter_by(company_id=company.id).delete()
        
        db.session.delete(company)
        db.session.commit()
        
        logger.info(f"Company deleted: {company_name} (ID: {company_id})")
        flash('Empresa y todos sus datos eliminados correctamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting company {company_id}: {e}")
        flash(f'Error al eliminar empresa: {str(e)}', 'error')
    
    return redirect(url_for('companies.list_companies'))


@companies_bp.route('/edit/<int:company_id>', methods=['GET', 'POST'])
@login_required
def edit_company(company_id):
    """Edit company details."""
    company = Company.query.get_or_404(company_id)
    
    if request.method == 'POST':
        company.rfc = request.form.get('rfc', '').strip().upper()
        company.name = request.form.get('name', '').strip()
        
        try:
            db.session.commit()
            logger.info(f"Company updated: {company.name} (ID: {company_id})")
            flash('Empresa actualizada correctamente.', 'success')
            return redirect(url_for('companies.list_companies'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating company {company_id}: {e}")
            flash(f'Error al actualizar empresa: {str(e)}', 'error')
    
    return render_template('edit_company.html', company=company)


@companies_bp.route('/sync/<int:company_id>', methods=['GET', 'POST'])
@login_required
def sync_company(company_id):
    """Sync invoices from SAT."""
    company = Company.query.get_or_404(company_id)
    
    if request.method == 'GET':
        # Get last invoice date
        last_invoice_date = db.session.query(
            db.func.max(Invoice.date)
        ).filter_by(company_id=company.id).scalar()
        
        if last_invoice_date:
            start_date = last_invoice_date.strftime('%Y-%m-%d')
        else:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        return render_template('sync.html', company=company, start_date=start_date, end_date=end_date)
    
    # POST - Process sync
    start_date_str = request.form['start_date']
    end_date_str = request.form['end_date']
    fiel_password = request.form['fiel_password']
    fiel_cer = request.files['fiel_cer']
    fiel_key = request.files['fiel_key']
    
    cer_path = None
    key_path = None
    
    try:
        # Save temporary files
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
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        
        # Download both Received and Emitted invoices
        received_invoices = sat_service.download_received_invoices(start_date, end_date)
        emitted_invoices = sat_service.download_emitted_invoices(start_date, end_date)
        all_invoices = received_invoices + emitted_invoices
        
        # Create folder structure for saving invoices
        safe_company_name = re.sub(r'[<>:"/\\|?*]', '_', company.name)
        invoices_folder = os.path.join(os.path.dirname(__file__), '..', 'facturas', safe_company_name)
        os.makedirs(invoices_folder, exist_ok=True)
        
        # Process invoices
        count = 0
        files_saved = 0
        
        for inv_data in all_invoices:
            # Save XML to file
            xml_filename = f"{inv_data['uuid']}.xml"
            xml_filepath = os.path.join(invoices_folder, xml_filename)
            if not os.path.exists(xml_filepath):
                with open(xml_filepath, 'w', encoding='utf-8') as xml_file:
                    xml_file.write(inv_data['xml'])
                files_saved += 1
            
            # Check if exists in database
            if not Invoice.query.filter_by(uuid=inv_data['uuid']).first():
                new_inv = Invoice(
                    uuid=inv_data['uuid'],
                    company_id=company.id,
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
                    periodicity=inv_data.get('periodicity'),
                    months=inv_data.get('months'),
                    fiscal_year=inv_data.get('fiscal_year'),
                    payment_terms=inv_data.get('payment_terms'),
                    currency=inv_data.get('currency'),
                    exchange_rate=inv_data.get('exchange_rate'),
                    exportation=inv_data.get('exportation'),
                    version=inv_data.get('version')
                )
                db.session.add(new_inv)
                
                # Determine Movement Type
                is_emitted = (inv_data['issuer_rfc'] == company.rfc)
                mov_type = 'INCOME' if is_emitted else 'EXPENSE'
                
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
        
        logger.info(f"Sync completed for {company.name}: {count} new invoices, {files_saved} files saved")
        
        if count > 0 or files_saved > 0:
            flash(f'Sincronización completada. {count} facturas nuevas en BD, {files_saved} archivos XML guardados.', 'success')
        else:
            flash('Sincronización finalizada. No se encontraron facturas nuevas.', 'warning')
        
    except SATError as sat_e:
        logger.error(f'SAT error for company {company.rfc}: Code={sat_e.code}, Message={sat_e.mensaje}')
        flash(sat_e.get_user_message(), 'error')
    except Exception as e:
        logger.exception(f"Sync error for company {company_id}")
        # Translate technical errors to user-friendly messages
        error_str = str(e).lower()
        if 'invalid fiel' in error_str or 'password' in error_str or 'decrypt' in error_str:
            user_message = 'La contraseña FIEL es incorrecta o los archivos no son válidos.'
        elif 'certificado' in error_str or 'certificate' in error_str or 'expired' in error_str:
            user_message = 'El certificado FIEL está expirado o no es válido.'
        elif 'timeout' in error_str or 'connection' in error_str:
            user_message = 'No se pudo conectar con el SAT. Por favor intente más tarde.'
        else:
            user_message = 'Ocurrió un error durante la sincronización. Por favor intente nuevamente.'
        flash(user_message, 'error')
    
    finally:
        # Cleanup temp files
        if cer_path and os.path.exists(cer_path):
            os.remove(cer_path)
        if key_path and os.path.exists(key_path):
            os.remove(key_path)
    
    return redirect(url_for('companies.list_companies'))


@companies_bp.route('/csf/<int:company_id>', methods=['GET', 'POST'])
@login_required
def download_csf(company_id):
    """Download CSF (not currently supported)."""
    flash('La descarga de CSF (Constancia de Situación Fiscal) no está disponible actualmente.', 'warning')
    return redirect(url_for('companies.list_companies'))
