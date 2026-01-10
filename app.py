from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
import os
import logging

# Load environment variables FIRST (before importing config)
from dotenv import load_dotenv
load_dotenv()

from config import Config
from extensions import db, login_manager, migrate, mail, cache, csrf, init_extensions
from models import Company, Movement, Invoice, User, Category, Supplier, TaxPayment, Product, InventoryTransaction, ProductBatch, FinkokCredentials, InvoiceFolioCounter, Customer
from forms import (LoginForm, RegistrationForm, CompanyForm, CompanyEditForm, SyncForm, TaxPaymentForm, 
                   CategoryForm, SupplierForm, InvoiceSearchForm, ProductForm, BatchForm, 
                   FinkokCredentialsForm, TimbrarFacturaForm, ConsultarEstadoForm, Lista69BForm,
                   CFDIComprobanteForm, CFDIReceptorForm, CFDIConceptoForm)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from services.sat_service import SATService, SATError
from services.qr_service import QRService
from sqlalchemy import func, extract
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Define project root directory (absolute path to the directory containing app.py)
# This ensures correct paths even in WSGI context where os.getcwd() returns wrong directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def get_or_create_supplier(company_id, rfc, business_name):
    """
    Obtiene o crea un proveedor y actualiza su información básica.
    
    Args:
        company_id: ID de la empresa
        rfc: RFC del proveedor
        business_name: Razón social del proveedor
        
    Returns:
        Supplier: Objeto del proveedor
    """
    supplier = Supplier.query.filter_by(
        company_id=company_id,
        rfc=rfc
    ).first()
    
    if not supplier:
        supplier = Supplier(
            company_id=company_id,
            rfc=rfc,
            business_name=business_name or rfc,
            active=True
        )
        db.session.add(supplier)
        db.session.flush()  # Para obtener el ID
    else:
        # Actualizar nombre si viene más completo
        if business_name and len(business_name) > len(supplier.business_name or ''):
            supplier.business_name = business_name
    
    return supplier


def update_supplier_stats(supplier_id):
    """
    Recalcula las estadísticas de un proveedor basándose en sus facturas.
    
    Args:
        supplier_id: ID del proveedor
    """
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return
    
    invoices = Invoice.query.filter_by(supplier_id=supplier_id).all()
    
    if invoices:
        supplier.invoice_count = len(invoices)
        supplier.total_invoiced = sum(inv.total for inv in invoices)
        supplier.first_invoice_date = min(inv.date for inv in invoices)
        supplier.last_invoice_date = max(inv.date for inv in invoices)
    else:
        supplier.invoice_count = 0
        supplier.total_invoiced = 0
        supplier.first_invoice_date = None
        supplier.last_invoice_date = None


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize all extensions
    init_extensions(app)
    
    # Setup logging
    from logging_config import setup_logging
    setup_logging(app)
    
    # Custom Jinja2 filter for currency formatting with thousands separators
    @app.template_filter('format_currency')
    def format_currency(value):
        """Format a number with thousand separators and 2 decimal places.
        Example: 1000000 -> 1,000,000.00
        """
        try:
            return "{:,.2f}".format(float(value))
        except (ValueError, TypeError):
            return "0.00"

    @app.template_filter('chunk_split')
    def chunk_split(body, chunklen=76, end='\r\n'):
        if not body: return ""
        return end.join(body[i:i+chunklen] for i in range(0, len(body), chunklen))

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('index'))
            else:
                flash('Usuario o contraseña incorrectos')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/change_password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        if request.method == 'POST':
            current_password = request.form['current_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']

            if not check_password_hash(current_user.password_hash, current_password):
                flash('La contraseña actual es incorrecta.', 'error')
                return redirect(url_for('change_password'))
            
            if new_password != confirm_password:
                flash('Las nuevas contraseñas no coinciden.', 'error')
                return redirect(url_for('change_password'))
            
            # Update password
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            
            flash('Tu contraseña ha sido actualizada correctamente.', 'success')
            return redirect(url_for('index'))
            
        return render_template('change_password.html')

    @app.route('/')
    @login_required
    def index():
        # Get all companies for selector
        companies = Company.query.all()
        
        # Get selected company from query parameter
        company_id = request.args.get('company_id', type=int)
        selected_company = None
        if company_id:
            selected_company = Company.query.get(company_id)
        
        # Base queries
        income_query = db.session.query(db.func.sum(Movement.amount)).filter(Movement.type == 'INCOME')
        expenses_query = db.session.query(db.func.sum(Movement.amount)).filter(Movement.type == 'EXPENSE')
        
        # Apply company filter if selected
        if company_id:
            income_query = income_query.filter(Movement.company_id == company_id)
            expenses_query = expenses_query.filter(Movement.company_id == company_id)
        
        # Calculate totals
        income = income_query.scalar() or 0
        expenses = expenses_query.scalar() or 0
        
        # Calculate monthly statistics (all 12 months of current year)
        today = datetime.now()
        current_year = today.year
        current_month = today.month
        monthly_data = []
        month_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                       'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        
        # Calculate all 12 months for the current year
        for month_num in range(1, 13):
            # Only include months up to current month
            if month_num > current_month:
                continue
                
            # Income for this month
            month_income_query = db.session.query(func.sum(Movement.amount)).filter(
                Movement.type == 'INCOME',
                extract('month', Movement.date) == month_num,
                extract('year', Movement.date) == current_year
            )
            
            # Expenses for this month
            month_expense_query = db.session.query(func.sum(Movement.amount)).filter(
                Movement.type == 'EXPENSE',
                extract('month', Movement.date) == month_num,
                extract('year', Movement.date) == current_year
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
        
        # Calculate annual statistics (current year)
        current_year = today.year
        annual_income_query = db.session.query(func.sum(Movement.amount)).filter(
            Movement.type == 'INCOME',
            extract('year', Movement.date) == current_year
        )
        annual_expense_query = db.session.query(func.sum(Movement.amount)).filter(
            Movement.type == 'EXPENSE',
            extract('year', Movement.date) == current_year
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
        
        return render_template('dashboard.html',
            companies=companies,
            selected_company=selected_company,
            income=income,
            expenses=expenses,
            inventory_value=inventory_value,
            monthly_data=monthly_data,
            annual_stats={
                'year': current_year,
                'income': float(annual_income),
                'expenses': float(annual_expense),
                'balance': float(annual_income - annual_expense)
            }
        )

    @app.route('/companies')
    @login_required
    def companies():
        companies_list = Company.query.all()
        return render_template('companies.html', companies=companies_list)

    @app.route('/companies/add', methods=['POST'])
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
        
        return redirect(url_for('companies'))

    @app.route('/companies/delete/<int:company_id>', methods=['POST'])
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
            
        return redirect(url_for('companies'))

    @app.route('/companies/edit/<int:company_id>', methods=['GET', 'POST'])
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
                return redirect(url_for('companies'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error al actualizar empresa: {str(e)}', 'error')
                
        return render_template('edit_company.html', company=company)

    @app.route('/companies/sync/<int:company_id>', methods=['GET', 'POST'])
    @login_required
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
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                
            end_date = datetime.now().strftime('%Y-%m-%d')
            
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
            
        return redirect(url_for('companies'))

    @app.route('/companies/csf/<int:company_id>', methods=['GET', 'POST'])
    @login_required
    def download_csf_route(company_id):
        flash('La descarga de CSF (Constancia de Situación Fiscal) no está disponible actualmente.', 'warning')
        return redirect(url_for('companies'))
    
    # Original CSF logic removed as CIEC is not supported
    #     company = Company.query.get_or_404(company_id)
    #     if request.method == 'GET':
    #         return render_template('csf_auth.html', company=company)
    #     ...

    @app.route('/invoices/<uuid>/download/<file_type>')
    @login_required
    def download_invoice_file(uuid, file_type):
        """
        Descarga el archivo XML o genera y descarga PDF de una factura.
        
        Args:
            uuid: UUID de la factura
            file_type: 'xml' o 'pdf'
        """
        invoice = Invoice.query.filter_by(uuid=uuid).first_or_404()
        
        # TODO: Agregar verificación de que el usuario tenga acceso a esta empresa
        # if invoice.company_id not in user_accessible_companies:
        #     abort(403)
        
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
                return redirect(request.referrer or url_for('index'))
        else:
            from flask import abort
            abort(400)

    @app.route('/logos/<filename>')
    def serve_logo(filename):
        """Servir archivos de logos de empresas"""
        from flask import send_from_directory
        logos_dir = os.path.join(os.path.dirname(__file__), 'logos')
        return send_from_directory(logos_dir, filename)


    @app.route('/movements')
    @login_required
    def movements():
        """Redirect to unified search/movements page"""
        return redirect(url_for('search_advanced'))
    
    @app.route('/companies/<int:company_id>/movements')
    @login_required
    def company_movements(company_id):
        """Redirect to unified search page for specific company"""
        return redirect(url_for('search_invoices', company_id=company_id))
    
    @app.route('/sync')
    @login_required
    def sync_list():
        """Show list of companies to sync"""
        companies_list = Company.query.all()
        return render_template('sync_list.html', companies=companies_list)
    
    @app.route('/categories')
    @login_required
    def categories_list():
        """Show list of companies to manage categories"""
        companies_list = Company.query.all()
        return render_template('categories_list.html', companies=companies_list)
    
    @app.route('/suppliers')
    @login_required
    def suppliers_list():
        """Show list of companies to manage suppliers"""
        companies_list = Company.query.all()
        return render_template('suppliers_list.html', companies=companies_list)
    
    @app.route('/search/advanced')
    @login_required
    def search_advanced():
        """Show list of companies for advanced search"""
        companies_list = Company.query.all()
        return render_template('search_list.html', companies=companies_list)
    
    @app.route('/taxes')
    @login_required
    def taxes_list():
        """Show list of companies for tax calculations"""
        companies_list = Company.query.all()
        return render_template('taxes_list.html', companies=companies_list)
    
    # ==================== DASHBOARD ROUTES ====================
    
    @app.route('/companies/<int:company_id>/dashboard')
    @login_required
    def company_dashboard(company_id):
        """Dashboard financiero principal de la empresa"""
        company = Company.query.get_or_404(company_id)
        
        # Obtener año seleccionado desde query parameter, por defecto el año actual
        today = datetime.now()
        try:
            selected_year = int(request.args.get('year', today.year))
        except (ValueError, TypeError):
            selected_year = today.year
        
        current_month = today.month
        current_year = today.year
        
        # Totales del mes actual del año seleccionado
        month_income = db.session.query(func.sum(Movement.amount)).filter(
            Movement.company_id == company_id,
            Movement.type == 'INCOME',
            extract('month', Movement.date) == current_month,
            extract('year', Movement.date) == selected_year
        ).scalar() or 0
        
        month_expense = db.session.query(func.sum(Movement.amount)).filter(
            Movement.company_id == company_id,
            Movement.type == 'EXPENSE',
            extract('month', Movement.date) == current_month,
            extract('year', Movement.date) == selected_year
        ).scalar() or 0
        
        # Totales del año seleccionado
        total_income = db.session.query(func.sum(Movement.amount)).filter(
            Movement.company_id == company_id,
            Movement.type == 'INCOME',
            extract('year', Movement.date) == selected_year
        ).scalar() or 0
        
        total_expense = db.session.query(func.sum(Movement.amount)).filter(
            Movement.company_id == company_id,
            Movement.type == 'EXPENSE',
            extract('year', Movement.date) == selected_year
        ).scalar() or 0
        
        # Tendencia de los 12 meses del año seleccionado
        monthly_trend = []
        for month in range(1, 13):  # Enero a Diciembre
            income = db.session.query(func.sum(Movement.amount)).filter(
                Movement.company_id == company_id,
                Movement.type == 'INCOME',
                extract('month', Movement.date) == month,
                extract('year', Movement.date) == selected_year
            ).scalar() or 0
            
            expense = db.session.query(func.sum(Movement.amount)).filter(
                Movement.company_id == company_id,
                Movement.type == 'EXPENSE',
                extract('month', Movement.date) == month,
                extract('year', Movement.date) == selected_year
            ).scalar() or 0
            
            month_name = datetime(selected_year, month, 1).strftime('%B')
            monthly_trend.append({
                'month': month_name,
                'income': float(income),
                'expense': float(expense)
            })
        
        # Distribución por categoría (solo egresos del año seleccionado)
        category_distribution = db.session.query(
            Category.name,
            Category.color,
            func.sum(Movement.amount).label('total')
        ).join(Movement).filter(
            Movement.company_id == company_id,
            Movement.type == 'EXPENSE',
            Category.active == True,
            extract('year', Movement.date) == selected_year
        ).group_by(Category.id).order_by(func.sum(Movement.amount).desc()).limit(8).all()
        
        # Últimas 10 facturas del año seleccionado
        recent_invoices = Invoice.query.filter(
            Invoice.company_id == company_id,
            extract('year', Invoice.date) == selected_year
        ).order_by(Invoice.date.desc()).limit(10).all()
        
        # Top 5 proveedores del año seleccionado
        # Calculamos basándonos en facturas del año
        from sqlalchemy import and_
        
        top_suppliers_query = db.session.query(
            Supplier,
            func.sum(Invoice.total).label('year_total'),
            func.count(Invoice.id).label('year_count')
        ).join(
            Invoice,
            and_(
                Invoice.receiver_rfc == Supplier.rfc,
                Invoice.company_id == company_id,
                extract('year', Invoice.date) == selected_year
            )
        ).filter(
            Supplier.company_id == company_id,
            Supplier.active == True
        ).group_by(Supplier.id).order_by(func.sum(Invoice.total).desc()).limit(5).all()
        
        # Formatear datos de proveedores
        top_suppliers = []
        for supplier, year_total, year_count in top_suppliers_query:
            supplier.total_invoiced = year_total or 0
            supplier.invoice_count = year_count or 0
            top_suppliers.append(supplier)
        
        # Calculate Inventory Value (Cost Price) - siempre valor actual
        inventory_value = db.session.query(
            func.sum(Product.current_stock * Product.cost_price)
        ).filter(
            Product.company_id == company_id,
            Product.active == True
        ).scalar() or 0
        
        return render_template('dashboard/company_dashboard.html',
            company=company,
            selected_year=selected_year,
            current_year=current_year,
            current_month=today.strftime('%B'),
            month_income=month_income,
            month_expense=month_expense,
            month_balance=month_income - month_expense,
            total_income=total_income,
            total_expense=total_expense,
            total_balance=total_income - total_expense,
            monthly_trend=monthly_trend,
            category_distribution=category_distribution,
            recent_invoices=recent_invoices,
            top_suppliers=top_suppliers,
            inventory_value=inventory_value
        )

    
    # ==================== SUPPLIER ROUTES ====================
    
    @app.route('/companies/<int:company_id>/suppliers')
    @login_required
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
    
    @app.route('/companies/<int:company_id>/suppliers/<int:supplier_id>')
    @login_required
    def supplier_detail(company_id, supplier_id):
        """Detalle de un proveedor específico con sus facturas"""
        company = Company.query.get_or_404(company_id)
        supplier = Supplier.query.get_or_404(supplier_id)
        
        # Verificar que el proveedor pertenece a esta empresa
        if supplier.company_id != company_id:
            flash('Proveedor no encontrado', 'error')
            return redirect(url_for('suppliers', company_id=company_id))
        
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
    
    # ==================== CATEGORY ROUTES ====================
    
    @app.route('/companies/<int:company_id>/categories')
    @login_required
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
    
    @app.route('/companies/<int:company_id>/categories/create', methods=['GET', 'POST'])
    @login_required
    def create_category(company_id):
        """Crear nueva categoría"""
        company = Company.query.get_or_404(company_id)
        
        if request.method == 'POST':
            name = request.form.get('name')
            cat_type = request.form.get('type')
            description = request.form.get('description')
            color = request.form.get('color', '#6c757d')
            
            category = Category(
                company_id=company_id,
                name=name,
                type=cat_type,
                description=description,
                color=color,
                is_default=False
            )
            
            db.session.add(category)
            db.session.commit()
            
            flash(f'Categoría "{name}" creada exitosamente', 'success')
            return redirect(url_for('categories', company_id=company_id))
        
        return render_template('categories/create.html', company=company)
    
    @app.route('/companies/<int:company_id>/categories/<int:category_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_category(company_id, category_id):
        """Editar categoría existente"""
        company = Company.query.get_or_404(company_id)
        category = Category.query.get_or_404(category_id)
        
        if category.company_id != company_id:
            flash('Categoría no encontrada', 'error')
            return redirect(url_for('categories', company_id=company_id))
        
        if request.method == 'POST':
            category.name = request.form.get('name')
            category.description = request.form.get('description')
            category.color = request.form.get('color')
            
            db.session.commit()
            flash(f'Categoría "{category.name}" actualizada', 'success')
            return redirect(url_for('categories', company_id=company_id))
        

    

    # ==================== PPD MANAGEMENT ROUTES ====================

    @app.route('/companies/<int:company_id>/ppd')
    @login_required
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
            current_year=datetime.now().year
        )

    @app.route('/companies/<int:company_id>/ppd/<int:invoice_id>/acreditar', methods=['POST'])
    @login_required
    def ppd_acreditar(company_id, invoice_id):
        """Acreditar una factura PPD a un mes específico"""
        company = Company.query.get_or_404(company_id)
        invoice = Invoice.query.get_or_404(invoice_id)
        
        if invoice.company_id != company_id:
            flash('Factura no encontrada', 'error')
            return redirect(url_for('ppd_list', company_id=company_id))
            
        if invoice.metodo_pago != 'PPD':
            flash('Solo se pueden acreditar facturas PPD', 'error')
            return redirect(url_for('ppd_list', company_id=company_id))
            
        mes = request.form.get('mes_acreditado', type=int)
        anio = request.form.get('anio_acreditado', type=int)
        
        if not mes or not anio:
            flash('Debe seleccionar mes y año', 'error')
            return redirect(url_for('ppd_list', company_id=company_id))
            
        try:
            from datetime import datetime
            
            # 1. Update Invoice status
            invoice.ppd_acreditado = True
            invoice.ppd_mes_acreditado = mes
            invoice.ppd_anio_acreditado = anio
            invoice.ppd_fecha_acreditacion = datetime.now()
            
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
            
        return redirect(url_for('ppd_list', company_id=company_id))

    @app.route('/companies/<int:company_id>/ppd/<int:invoice_id>/desacreditar', methods=['POST'])
    @login_required
    def ppd_desacreditar(company_id, invoice_id):
        """Remover acreditación de una factura PPD"""
        company = Company.query.get_or_404(company_id)
        invoice = Invoice.query.get_or_404(invoice_id)
        
        if invoice.company_id != company_id:
            flash('Factura no encontrada', 'error')
            return redirect(url_for('ppd_list', company_id=company_id))
            
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
            
        return redirect(url_for('ppd_list', company_id=company_id))

    # ==================== INVENTORY ROUTES ====================

    @app.route('/inventory')
    @login_required
    def inventory_companies_list():
        """Show list of companies for inventory management"""
        companies_list = Company.query.all()
        return render_template('inventory_list_companies.html', companies=companies_list)

    @app.route('/companies/<int:company_id>/inventory')
    @login_required
    def inventory_list(company_id):
        """Listado de productos e inventario"""
        company = Company.query.get_or_404(company_id)
        products = Product.query.filter_by(company_id=company_id, active=True).order_by(Product.name).all()
        
        # Calculate total inventory value (Cost Price * Stock)
        total_inventory_value = sum(p.current_stock * p.cost_price for p in products)
        total_items = sum(p.current_stock for p in products)
        
        return render_template('inventory/list.html', 
                               company=company, 
                               products=products,
                               total_inventory_value=total_inventory_value,
                               total_items=total_items)

    @app.route('/companies/<int:company_id>/inventory/add', methods=['GET', 'POST'])
    @login_required
    def add_product(company_id):
        """Agregar nuevo producto"""
        company = Company.query.get_or_404(company_id)
        form = ProductForm()
        
        if form.validate_on_submit():
            new_product = Product(
                company_id=company_id,
                name=form.name.data,
                sku=form.sku.data,
                description=form.description.data,
                cost_price=form.cost_price.data or 0,
                selling_price=form.selling_price.data or 0,
                current_stock=form.initial_stock.data or 0,
                min_stock_level=form.min_stock_level.data or 0,
                # COFEPRIS Fields
                sanitary_registration=form.sanitary_registration.data,
                is_controlled=form.is_controlled.data,
                active_ingredient=form.active_ingredient.data,
                presentation=form.presentation.data,
                therapeutic_group=form.therapeutic_group.data,
                unit_measure=form.unit_measure.data
            )
            
            db.session.add(new_product)
            db.session.flush() # Get ID
            
            # Record initial stock as transaction if > 0
            if new_product.current_stock > 0:
                transaction = InventoryTransaction(
                    product_id=new_product.id,
                    type='IN',
                    quantity=new_product.current_stock,
                    previous_stock=0,
                    new_stock=new_product.current_stock,
                    reference='Initial Stock',
                    notes='Inventario inicial al crear producto'
                )
                db.session.add(transaction)
            
            db.session.commit()
            flash(f'Producto "{new_product.name}" agregado correctamente.', 'success')
            return redirect(url_for('inventory_list', company_id=company_id))
            
        return render_template('inventory/add.html', company=company, form=form)

    @app.route('/companies/<int:company_id>/inventory/<int:product_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_product(company_id, product_id):
        """Editar producto"""
        company = Company.query.get_or_404(company_id)
        product = Product.query.get_or_404(product_id)
        
        if product.company_id != company_id:
            flash('Producto no encontrado.', 'error')
            return redirect(url_for('inventory_list', company_id=company_id))
            
        form = ProductForm(obj=product)
        
        if form.validate_on_submit():
            form.populate_obj(product)
            db.session.commit()
            flash(f'Producto "{product.name}" actualizado.', 'success')
            return redirect(url_for('inventory_list', company_id=company_id))
            
        return render_template('inventory/edit.html', company=company, product=product, form=form)

    @app.route('/companies/<int:company_id>/inventory/<int:product_id>/adjust', methods=['GET', 'POST'])
    @login_required
    def adjust_stock(company_id, product_id):
        """Ajuste manual de stock"""
        company = Company.query.get_or_404(company_id)
        product = Product.query.get_or_404(product_id)
        
        if product.company_id != company_id:
            flash('Producto no encontrado.', 'error')
            return redirect(url_for('inventory_list', company_id=company_id))
            
        if request.method == 'POST':
            adjustment_type = request.form['type'] # 'IN' or 'OUT'
            quantity = int(request.form['quantity'])
            notes = request.form.get('notes')
            
            if quantity <= 0:
                flash('La cantidad debe ser mayor a 0.', 'error')
                return redirect(url_for('adjust_stock', company_id=company_id, product_id=product_id))
            
            previous_stock = product.current_stock
            new_stock = previous_stock
            
            if adjustment_type == 'IN':
                new_stock += quantity
            elif adjustment_type == 'OUT':
                if previous_stock < quantity:
                    flash('No hay suficiente stock para realizar esta salida.', 'error')
                    return redirect(url_for('adjust_stock', company_id=company_id, product_id=product_id))
                new_stock -= quantity
                
            product.current_stock = new_stock
            
            transaction = InventoryTransaction(
                product_id=product.id,
                type=adjustment_type,
                quantity=quantity,
                previous_stock=previous_stock,
                new_stock=new_stock,
                reference='Manual Adjustment',
                notes=notes
            )
            
            db.session.add(transaction)
            db.session.commit()
            
            flash('Inventario actualizado correctamente.', 'success')
            return redirect(url_for('inventory_list', company_id=company_id))
            
        return render_template('inventory/adjust.html', company=company, product=product)

    @app.route('/companies/<int:company_id>/inventory/<int:product_id>/history')
    @login_required
    def product_history(company_id, product_id):
        """Historial de movimientos de un producto"""
        company = Company.query.get_or_404(company_id)
        product = Product.query.get_or_404(product_id)
        
        if product.company_id != company_id:
            return redirect(url_for('inventory_list', company_id=company_id))
            
        return render_template('inventory/history.html', company=company, product=product)

    @app.route('/companies/<int:company_id>/inventory/<int:product_id>/batches')
    @login_required
    def product_batches(company_id, product_id):
        """List batches for a product"""
        company = Company.query.get_or_404(company_id)
        product = Product.query.get_or_404(product_id)
        
        if product.company_id != company_id:
            return redirect(url_for('inventory_list', company_id=company_id))
            
        today = datetime.now().date()
        batches = ProductBatch.query.filter_by(product_id=product_id).order_by(ProductBatch.expiration_date).all()
        
        return render_template('inventory/batches.html', 
                             company=company, 
                             product=product, 
                             batches=batches, 
                             today=today)

    @app.route('/companies/<int:company_id>/inventory/<int:product_id>/receive', methods=['GET', 'POST'])
    @login_required
    def receive_batch(company_id, product_id):
        """Recibir stock con lote y caducidad"""
        company = Company.query.get_or_404(company_id)
        product = Product.query.get_or_404(product_id)
        
        if product.company_id != company_id:
            return redirect(url_for('inventory_list', company_id=company_id))
            
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
                notes='Recepción de stock con lote'
            )
            db.session.add(transaction)
            
            # Update Product Total Stock
            product.current_stock += quantity
            
            db.session.commit()
            flash(f'Lote {batch.batch_number} registrado correctamente.', 'success')
            return redirect(url_for('product_batches', company_id=company_id, product_id=product_id))
            
        return render_template('inventory/receive_batch.html', company=company, product=product, form=form)

    
    # ==================== AX MANAGMENT ROUTES ====================

    @app.route('/companies/<int:company_id>/taxes')
    @login_required
    def taxes_dashboard(company_id):
        """Dashboard de Impuestos con IVA, ISR y resumen anual"""
        company = Company.query.get_or_404(company_id)
        
        today = datetime.now()
        current_year = today.year
        
        # Calculate monthly tax data
        monthly_tax_data = []
        month_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                       'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        
        # Annual totals
        annual_iva_to_pay = 0
        annual_iva_paid = 0
        annual_isr_estimated = 0
        annual_isr_paid = 0
        annual_income = 0
        annual_expense = 0
        
        # Chart data arrays
        chart_months = []
        chart_iva_collected = []
        chart_iva_deductible = []
        chart_isr_estimated = []
        
        for month_num in range(1, 13):
            # IVA Trasladado (Cobrado en Ventas) - invoices where company is the issuer
            iva_collected = db.session.query(func.sum(Invoice.tax)).filter(
                Invoice.company_id == company_id,
                Invoice.issuer_rfc == company.rfc,  # Company issued this invoice (income)
                extract('month', Invoice.date) == month_num,
                extract('year', Invoice.date) == current_year
            ).scalar() or 0
            
            # IVA Acreditable (Pagado en Gastos) - invoices where company is the receiver
            iva_deductible = db.session.query(func.sum(Invoice.tax)).filter(
                Invoice.company_id == company_id,
                Invoice.receiver_rfc == company.rfc,  # Company received this invoice (expense)
                extract('month', Invoice.date) == month_num,
                extract('year', Invoice.date) == current_year
            ).scalar() or 0
            
            # Ingresos del mes (para ISR) - invoices where company is the issuer
            month_income = db.session.query(func.sum(Invoice.subtotal)).filter(
                Invoice.company_id == company_id,
                Invoice.issuer_rfc == company.rfc,  # Company issued this invoice (income)
                extract('month', Invoice.date) == month_num,
                extract('year', Invoice.date) == current_year
            ).scalar() or 0
            
            # Egresos del mes (para ISR) - invoices where company is the receiver
            month_expense = db.session.query(func.sum(Invoice.subtotal)).filter(
                Invoice.company_id == company_id,
                Invoice.receiver_rfc == company.rfc,  # Company received this invoice (expense)
                extract('month', Invoice.date) == month_num,
                extract('year', Invoice.date) == current_year
            ).scalar() or 0
            
            # Net IVA Position (+ a pagar, - a favor)
            net_iva = iva_collected - iva_deductible
            
            # ISR Estimado (30% de utilidad bruta, solo si es positiva)
            profit = month_income - month_expense
            isr_estimated = max(0, profit * 0.30)
            
            # IVA Payments made
            iva_payments = TaxPayment.query.filter_by(
                company_id=company_id,
                period_month=month_num,
                period_year=current_year,
                tax_type='IVA'
            ).all()
            iva_paid_amount = sum(p.amount for p in iva_payments)
            
            # ISR Payments made
            isr_payments = TaxPayment.query.filter_by(
                company_id=company_id,
                period_month=month_num,
                period_year=current_year,
                tax_type='ISR'
            ).all()
            isr_paid_amount = sum(p.amount for p in isr_payments)
            
            # Accumulate annual totals
            if net_iva > 0:
                annual_iva_to_pay += net_iva
            annual_iva_paid += iva_paid_amount
            annual_isr_estimated += isr_estimated
            annual_isr_paid += isr_paid_amount
            annual_income += month_income
            annual_expense += month_expense
            
            # Chart data
            chart_months.append(month_names[month_num - 1][:3])  # Abbreviated
            chart_iva_collected.append(float(iva_collected))
            chart_iva_deductible.append(float(iva_deductible))
            chart_isr_estimated.append(float(isr_estimated))
            
            monthly_tax_data.append({
                'month_num': month_num,
                'month_name': month_names[month_num - 1],
                'iva_collected': float(iva_collected),
                'iva_deductible': float(iva_deductible),
                'net_iva': float(net_iva),
                'iva_paid_amount': float(iva_paid_amount),
                'iva_difference': float(net_iva - iva_paid_amount),
                'income': float(month_income),
                'expense': float(month_expense),
                'profit': float(profit),
                'isr_estimated': float(isr_estimated),
                'isr_paid_amount': float(isr_paid_amount),
                'isr_difference': float(isr_estimated - isr_paid_amount)
            })
        
        # Annual summary
        annual_summary = {
            'iva_to_pay': float(annual_iva_to_pay),
            'iva_paid': float(annual_iva_paid),
            'iva_pending': float(annual_iva_to_pay - annual_iva_paid),
            'isr_estimated': float(annual_isr_estimated),
            'isr_paid': float(annual_isr_paid),
            'isr_pending': float(annual_isr_estimated - annual_isr_paid),
            'total_income': float(annual_income),
            'total_expense': float(annual_expense),
            'total_profit': float(annual_income - annual_expense)
        }
        
        # Chart data for JavaScript
        chart_data = {
            'months': chart_months,
            'iva_collected': chart_iva_collected,
            'iva_deductible': chart_iva_deductible,
            'isr_estimated': chart_isr_estimated
        }
            
        return render_template('taxes/dashboard.html', 
                             company=company, 
                             current_year=current_year,
                             monthly_tax_data=monthly_tax_data,
                             annual_summary=annual_summary,
                             chart_data=chart_data)

    @app.route('/companies/<int:company_id>/taxes/payment', methods=['POST'])
    @login_required
    def record_tax_payment(company_id):
        """Registrar pago de impuestos manual"""
        company = Company.query.get_or_404(company_id)
        
        try:
            month = int(request.form.get('month'))
            year = int(request.form.get('year'))
            amount = float(request.form.get('amount'))
            tax_type = request.form.get('tax_type', 'IVA')
            notes = request.form.get('notes')
            
            payment = TaxPayment(
                company_id=company_id,
                period_month=month,
                period_year=year,
                tax_type=tax_type,
                amount=amount,
                notes=notes,
                payment_date=datetime.now()
            )
            
            db.session.add(payment)
            db.session.commit()
            
            flash('Pago de impuestos registrado correctamente', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar pago: {str(e)}', 'error')
            
        return redirect(url_for('taxes_dashboard', company_id=company_id))
    
    # ==================== SALES ANALYTICS ROUTES ====================
    
    @app.route('/sales')
    @login_required
    def sales_list():
        """Show list of companies for sales analysis"""
        companies_list = Company.query.all()
        return render_template('sales_list.html', companies=companies_list)
    
    @app.route('/companies/<int:company_id>/sales')
    @login_required
    def sales_dashboard(company_id):
        """Dashboard de Análisis de Ventas con comparación año a año"""
        company = Company.query.get_or_404(company_id)
        
        today = datetime.now()
        
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
    
    @app.route('/companies/<int:company_id>/search')
    @login_required
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
    

    @app.route('/companies/<int:company_id>/invoices/<int:invoice_id>')
    @login_required
    def invoice_detail(company_id, invoice_id):
        """Detalle completo de una factura"""
        company = Company.query.get_or_404(company_id)
        invoice = Invoice.query.get_or_404(invoice_id)
        
        if invoice.company_id != company_id:
            flash('Factura no encontrada', 'error')
            return redirect(url_for('search_invoices', company_id=company_id))
            
        return render_template('invoices/detail.html', company=company, invoice=invoice)

    # ==================== QR CODE ROUTES ====================
    
    @app.route('/companies/<int:company_id>/qr')
    @login_required
    def company_qr(company_id):
        """Generate QR code for company"""
        company = Company.query.get_or_404(company_id)
        qr_base64 = QRService.generate_company_qr(company)
        return render_template('qr_display.html', 
            company=company, 
            qr_image=qr_base64,
            title=f'QR - {company.name}'
        )
    
    @app.route('/companies/<int:company_id>/qr/download')
    @login_required
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
    
    @app.route('/companies/<int:company_id>/invoices/<int:invoice_id>/qr')
    @login_required
    def invoice_qr(company_id, invoice_id):
        """Generate SAT verification QR for invoice"""
        invoice = Invoice.query.get_or_404(invoice_id)
        
        if invoice.company_id != company_id:
            flash('Factura no encontrada', 'error')
            return redirect(url_for('search_invoices', company_id=company_id))
        
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

    # ==================== API ROUTES ====================
    
    @app.route('/api/companies/<int:company_id>/stats')
    @login_required
    @cache.cached(timeout=60, query_string=True)
    def api_company_stats(company_id):
        """API endpoint para estadísticas en tiempo real (cached 60s)"""
        month = request.args.get('month', type=int)
        year = request.args.get('year', type=int)
        
        if not month or not year:
            today = datetime.now()
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

    # ==================== CUSTOMER API ROUTES ====================
    
    @app.route('/api/companies/<int:company_id>/customers/search')
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
    
    @app.route('/api/companies/<int:company_id>/customers/<rfc>')
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

    # ==================== CATÁLOGOS SAT API ====================
    
    @app.route('/api/catalogs/<catalog_type>/search')
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
    
    @app.route('/api/catalogs/<catalog_type>/<code>')
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

    # ==================== FACTURACIÓN ROUTES ====================
    
    @app.route('/facturacion')
    @login_required
    def facturacion_list():
        """Lista de empresas para acceder al módulo de facturación"""
        companies_list = Company.query.all()
        return render_template('facturacion/facturacion_list.html', companies=companies_list)
    
    @app.route('/companies/<int:company_id>/facturacion')
    @login_required
    def facturacion_dashboard(company_id):
        """Dashboard principal de facturación"""
        company = Company.query.get_or_404(company_id)
        
        # Check if Finkok credentials are configured
        credentials = FinkokCredentials.query.filter_by(company_id=company_id).first()
        has_credentials = credentials is not None
        environment = credentials.environment if credentials else None
        
        return render_template('facturacion/facturacion_dashboard.html',
            company=company,
            has_credentials=has_credentials,
            environment=environment
        )
    
    @app.route('/companies/<int:company_id>/facturacion/credenciales', methods=['GET', 'POST'])
    @login_required
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
                credentials.updated_at = datetime.utcnow()
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
                return redirect(url_for('facturacion_dashboard', company_id=company_id))
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
    
    @app.route('/companies/<int:company_id>/facturacion/download/<file_type>')
    @login_required
    def facturacion_download_timbrado(company_id, file_type):
        """Descargar archivo timbrado (XML o PDF)"""
        from flask import session, send_file
        
        result = session.get('timbrado_result')
        if not result or file_type not in result.get('files', {}):
            flash('Archivo no encontrado', 'error')
            return redirect(url_for('facturacion_timbrar', company_id=company_id))
        
        file_path = result['files'][file_type]
        mimetype = 'application/xml' if file_type == 'xml' else 'application/pdf'
        
        return send_file(
            file_path,
            mimetype=mimetype,
            as_attachment=True,
            download_name=f"{result['uuid']}.{file_type}"
        )
    
    @app.route('/companies/<int:company_id>/facturacion/estado', methods=['GET', 'POST'])
    @login_required
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
    
    @app.route('/companies/<int:company_id>/facturacion/lista69b', methods=['GET', 'POST'])
    @login_required
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
    # ==================== GENERADOR DE CFDI ROUTES ====================
    
    @app.route('/companies/<int:company_id>/facturacion/crear', methods=['GET', 'POST'])
    @login_required
    def crear_factura(company_id):
        """Generador de CFDI - Crear, generar XML y timbrar automáticamente"""
        company = Company.query.get_or_404(company_id)
        
        # Verificar que tenga credenciales Finkok
        credentials = FinkokCredentials.query.filter_by(company_id=company_id).first()
        if not credentials:
            flash('Debe configurar las credenciales de Finkok primero', 'warning')
            return redirect(url_for('facturacion_credenciales', company_id=company_id))
        
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
        
        return render_template('facturacion/crear_factura.html',
            company=company,
            form_comprobante=form_comprobante,
            form_receptor=form_receptor
        )
    
    
    def generar_y_timbrar_cfdi(company, credentials, form_comprobante, form_receptor):
        """Generar XML, timbrar y guardar en carpeta xml/[RFC]/"""
        try:
            from services.cfdi_generator import CFDIGenerator
            from services.facturacion_service import FacturacionService
            from utils.crypto import decrypt_password
            from werkzeug.utils import secure_filename
            import json
            import tempfile
            
            # Obtener conceptos
            conceptos_json = request.form.get('conceptos')
            if not conceptos_json:
                flash('Debe agregar al menos un concepto', 'error')
                return redirect(url_for('crear_factura', company_id=company.id))
            
            conceptos = json.loads(conceptos_json)
            
            # Procesar archivos FIEL
            fiel_cer_file = form_comprobante.fiel_cer.data
            fiel_key_file = form_comprobante.fiel_key.data
            fiel_password = form_comprobante.fiel_password.data
            
            if not fiel_cer_file or not fiel_key_file or not fiel_password:
                flash('Debe proporcionar certificado FIEL, llave privada y contraseña', 'error')
                return redirect(url_for('crear_factura', company_id=company.id))
            
            # Guardar FIEL temporalmente
            temp_dir = tempfile.gettempdir()
            cer_filename = secure_filename(fiel_cer_file.filename)
            key_filename = secure_filename(fiel_key_file.filename)
            
            cer_path = os.path.join(temp_dir, f"fiel_{company.id}_{cer_filename}")
            key_path = os.path.join(temp_dir, f"fiel_{company.id}_{key_filename}")
            
            fiel_cer_file.save(cer_path)
            fiel_key_file.save(key_path)
            
            try:
                # Generar XML
                generator = CFDIGenerator(
                    certificado_path=cer_path,
                    key_path=key_path,
                    key_password=fiel_password
                )
                
                # Validar
                validacion = generator.validar_datos(
                    receptor_rfc=form_receptor.receptor_rfc.data,
                    receptor_cp=form_receptor.receptor_cp.data,
                    receptor_regimen=form_receptor.receptor_regimen.data,
                    receptor_uso_cfdi=form_receptor.receptor_uso_cfdi.data,
                    lugar_expedicion=form_comprobante.lugar_expedicion.data,
                    conceptos=conceptos
                )
                
                if not validacion['valido']:
                    for error in validacion['errores']:
                        flash(error, 'error')
                    return redirect(url_for('crear_factura', company_id=company.id))
                
                # Generar CFDI (retorna tupla: objeto firmado, XML string)
                cfdi_firmado, xml_sin_timbrar = generator.crear_factura(
                    serie=form_comprobante.serie.data,
                    folio=form_comprobante.folio.data,
                    fecha=form_comprobante.fecha.data,
                    forma_pago=form_comprobante.forma_pago.data,
                    metodo_pago=form_comprobante.metodo_pago.data,
                    lugar_expedicion=form_comprobante.lugar_expedicion.data,
                    receptor_rfc=form_receptor.receptor_rfc.data,
                    receptor_nombre=form_receptor.receptor_nombre.data,
                    receptor_uso_cfdi=form_receptor.receptor_uso_cfdi.data,
                    receptor_regimen=form_receptor.receptor_regimen.data,
                    receptor_cp=form_receptor.receptor_cp.data,
                    conceptos=conceptos
                )
                
                # Crear carpeta xml/RFC_EMPRESA/ si no existe
                xml_base_dir = os.path.join(PROJECT_ROOT, 'xml')
                company_xml_dir = os.path.join(xml_base_dir, company.rfc)
                os.makedirs(company_xml_dir, exist_ok=True)
                
                # Timbrar con Finkok - pasar el objeto CFDI directamente
                password = decrypt_password(credentials.password_enc)
                facturacion_service = FacturacionService(
                    finkok_username=credentials.username,
                    finkok_password=password,
                    environment=credentials.environment
                )
                
                # CRÍTICO: Pasar el objeto CFDI, no el string XML
                result = facturacion_service.timbrar_factura(cfdi_firmado, accept='XML')
                
                if result['success']:
                    # Guardar XMLs en carpeta
                    uuid = result['uuid']
                    serie = form_comprobante.serie.data or ''
                    folio = form_comprobante.folio.data or 'SN'
                    
                    # Nombre del archivo
                    filename_base = f"{serie}{folio}_{uuid}"
                    
                    # Guardar XML timbrado
                    if 'xml' in result:
                        xml_path = os.path.join(company_xml_dir, f"{filename_base}.xml")
                        with open(xml_path, 'wb') as f:
                            f.write(result['xml'])
                        logger.info(f"XML timbrado guardado en: {xml_path}")
                    
                    # Guardar PDF
                    if 'pdf' in result:
                        pdf_path = os.path.join(company_xml_dir, f"{filename_base}.pdf")
                        with open(pdf_path, 'wb') as f:
                            f.write(result['pdf'])
                        logger.info(f"PDF guardado en: {pdf_path}")
                    
                    # INCREMENTAR CONTADOR DE FOLIO
                    # Obtener o crear el contador para esta serie
                    folio_counter = InvoiceFolioCounter.query.filter_by(
                        company_id=company.id,
                        serie=serie
                    ).first()
                    
                    if not folio_counter:
                        # Crear contador si no existe
                        folio_counter = InvoiceFolioCounter(
                            company_id=company.id,
                            serie=serie,
                            current_folio=0
                        )
                        db.session.add(folio_counter)
                    
                    # Extraer el número del folio (remover ceros a la izquierda)
                    try:
                        folio_num = int(folio)
                    except ValueError:
                        folio_num = 1
                    
                    # Actualizar el contador solo si el folio usado es mayor o igual al actual
                    if folio_num >= folio_counter.current_folio:
                        folio_counter.current_folio = folio_num
                        folio_counter.updated_at = datetime.now(timezone.utc)
                        db.session.commit()
                        logger.info(f"Contador de folio actualizado: Serie {serie}, Folio {folio_num}")
                    
                    # GUARDAR O ACTUALIZAR CLIENTE
                    receptor_rfc = form_receptor.receptor_rfc.data.upper().strip()
                    receptor_nombre = form_receptor.receptor_nombre.data.strip()
                    receptor_cp = form_receptor.receptor_cp.data.strip()
                    receptor_regimen = form_receptor.receptor_regimen.data
                    
                    # Buscar si el cliente ya existe
                    existing_customer = Customer.query.filter_by(
                        company_id=company.id,
                        rfc=receptor_rfc
                    ).first()
                    
                    if existing_customer:
                        # Actualizar datos del cliente si han cambiado
                        existing_customer.nombre = receptor_nombre
                        existing_customer.codigo_postal = receptor_cp
                        existing_customer.regimen_fiscal = receptor_regimen
                        existing_customer.updated_at = datetime.utcnow()
                        logger.info(f"Cliente actualizado: {receptor_rfc}")
                    else:
                        # Crear nuevo cliente
                        new_customer = Customer(
                            company_id=company.id,
                            rfc=receptor_rfc,
                            nombre=receptor_nombre,
                            codigo_postal=receptor_cp,
                            regimen_fiscal=receptor_regimen
                        )
                        db.session.add(new_customer)
                        logger.info(f"Nuevo cliente creado: {receptor_rfc}")
                    
                    db.session.commit()
                    
                    flash(f'✅ ¡Factura creada y timbrada exitosamente! UUID: {uuid}', 'success')
                    flash(f'📁 Archivos guardados en: xml/{company.rfc}/', 'info')
                    
                    return redirect(url_for('facturacion_dashboard', company_id=company.id))
                else:
                    # --- Save Failed XML (Timbrado Error) ---
                    try:
                        import time
                        import uuid as uuid_lib
                        from lxml import etree
                        
                        timestamp = int(time.time())
                        unique_id = uuid_lib.uuid4().hex[:8]
                        filename = f"FAILED_TIMBRADO_{timestamp}_{unique_id}.xml"
                        
                        fallidos_dir = os.path.join(PROJECT_ROOT, 'xml', 'fallidos')
                        os.makedirs(fallidos_dir, exist_ok=True)
                        filepath = os.path.join(fallidos_dir, filename)
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(xml_sin_timbrar)
                            
                        logger.info(f"XML rechazado por PAC guardado en: {filepath}")
                        flash(f'El XML generado fue guardado en xml/fallidos para revisión.', 'warning')
                        
                    except Exception as save_err:
                        logger.error(f"Error guardando XML fallido: {str(save_err)}")
                    
                    flash(f'Error al timbrar: {result["message"]}', 'error')
                    return redirect(url_for('crear_factura', company_id=company.id))
                    
            finally:
                # Limpiar archivos temporales
                if os.path.exists(cer_path):
                    os.remove(cer_path)
                if os.path.exists(key_path):
                    os.remove(key_path)
                
        except Exception as e:
            logger.error(f'Error al generar y timbrar: {str(e)}')
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('crear_factura', company_id=company.id))

    # Register CLI commands
    from cli import register_commands
    register_commands(app)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
