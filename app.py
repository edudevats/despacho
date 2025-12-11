from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
import os
import logging
from config import Config
from extensions import db, login_manager, migrate, mail, cache, csrf, init_extensions
from models import Company, Movement, Invoice, User, Category, Supplier, TaxPayment, Product, InventoryTransaction
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from services.sat_service import SATService
from services.qr_service import QRService
from sqlalchemy import func, extract
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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
        
        new_company = Company(
            rfc=rfc, 
            name=name
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
            files_saved = 0
            for inv_data in all_invoices:
                # Save XML to file first (always save, even if already in DB)
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
                        # New fields
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
                    # Simple rule: if company is the issuer (emisor) = INCOME
                    #              if company is the receiver = EXPENSE
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
            
            if count > 0 or files_saved > 0:
                flash(f'Sincronización completada. {count} facturas nuevas en BD, {files_saved} archivos XML guardados en facturas/{safe_company_name}/', 'success')
            else:
                flash(f'Sincronización finalizada. No se encontraron facturas nuevas. Las facturas existentes ya están en facturas/{safe_company_name}/', 'warning')
            
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
            elif 'rechaz' in error_str or '5002' in error_str:
                user_message = 'El SAT rechazó la solicitud. Intente con un rango de fechas diferente.'
            elif '5004' in error_str or 'no se encontr' in error_str:
                user_message = 'No se encontraron facturas en el rango de fechas seleccionado.'
            elif '5005' in error_str or 'duplicad' in error_str:
                user_message = 'Ya existe una solicitud en proceso. Por favor espere unos minutos.'
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

    @app.route('/movements')
    @login_required
    def movements():
        """Show list of companies for movements"""
        companies_list = Company.query.all()
        return render_template('movements_list.html', companies=companies_list)
    
    @app.route('/companies/<int:company_id>/movements')
    @login_required
    def company_movements(company_id):
        """Show movements for a specific company"""
        company = Company.query.get_or_404(company_id)
        movements_list = Movement.query.filter_by(company_id=company_id).order_by(Movement.date.desc()).all()
        return render_template('movements.html', movements=movements_list, company=company)
    
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
        
        # Fecha actual
        today = datetime.now()
        current_month = today.month
        current_year = today.year
        
        # Totales del mes actual
        month_income = db.session.query(func.sum(Movement.amount)).filter(
            Movement.company_id == company_id,
            Movement.type == 'INCOME',
            extract('month', Movement.date) == current_month,
            extract('year', Movement.date) == current_year
        ).scalar() or 0
        
        month_expense = db.session.query(func.sum(Movement.amount)).filter(
            Movement.company_id == company_id,
            Movement.type == 'EXPENSE',
            extract('month', Movement.date) == current_month,
            extract('year', Movement.date) == current_year
        ).scalar() or 0
        
        # Totales históricos
        total_income = db.session.query(func.sum(Movement.amount)).filter(
            Movement.company_id == company_id,
            Movement.type == 'INCOME'
        ).scalar() or 0
        
        total_expense = db.session.query(func.sum(Movement.amount)).filter(
            Movement.company_id == company_id,
            Movement.type == 'EXPENSE'
        ).scalar() or 0
        
        # Tendencia últimos 6 meses
        monthly_trend = []
        for i in range(5, -1, -1):
            month = today.month - i
            year = today.year
            
            if month <= 0:
                month += 12
                year -= 1
            
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
            
            month_name = datetime(year, month, 1).strftime('%B')
            monthly_trend.append({
                'month': month_name,
                'income': float(income),
                'expense': float(expense)
            })
        
        # Distribución por categoría (solo egresos)
        category_distribution = db.session.query(
            Category.name,
            Category.color,
            func.sum(Movement.amount).label('total')
        ).join(Movement).filter(
            Movement.company_id == company_id,
            Movement.type == 'EXPENSE',
            Category.active == True
        ).group_by(Category.id).order_by(func.sum(Movement.amount).desc()).limit(8).all()
        
        # Últimas 10 facturas
        recent_invoices = Invoice.query.filter_by(company_id=company_id).order_by(
            Invoice.date.desc()
        ).limit(10).all()
        
        # Top 5 proveedores
        top_suppliers = Supplier.query.filter_by(
            company_id=company_id,
            active=True
        ).order_by(Supplier.total_invoiced.desc()).limit(5).all()
        
        # Calculate Inventory Value (Cost Price)
        inventory_value = db.session.query(
            func.sum(Product.current_stock * Product.cost_price)
        ).filter(
            Product.company_id == company_id,
            Product.active == True
        ).scalar() or 0
        
        return render_template('dashboard/company_dashboard.html',
            company=company,
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
        
        if request.method == 'POST':
            name = request.form['name']
            sku = request.form.get('sku')
            description = request.form.get('description')
            cost_price = float(request.form.get('cost_price', 0))
            selling_price = float(request.form.get('selling_price', 0))
            initial_stock = int(request.form.get('initial_stock', 0))
            min_stock = int(request.form.get('min_stock', 0))
            
            new_product = Product(
                company_id=company_id,
                name=name,
                sku=sku,
                description=description,
                cost_price=cost_price,
                selling_price=selling_price,
                current_stock=initial_stock,
                min_stock_level=min_stock
            )
            
            db.session.add(new_product)
            db.session.flush() # Get ID
            
            # Record initial stock as transaction if > 0
            if initial_stock > 0:
                transaction = InventoryTransaction(
                    product_id=new_product.id,
                    type='IN',
                    quantity=initial_stock,
                    previous_stock=0,
                    new_stock=initial_stock,
                    reference='Initial Stock',
                    notes='Inventario inicial al crear producto'
                )
                db.session.add(transaction)
            
            db.session.commit()
            flash(f'Producto "{name}" agregado correctamente.', 'success')
            return redirect(url_for('inventory_list', company_id=company_id))
            
        return render_template('inventory/add.html', company=company)

    @app.route('/companies/<int:company_id>/inventory/<int:product_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_product(company_id, product_id):
        """Editar producto"""
        company = Company.query.get_or_404(company_id)
        product = Product.query.get_or_404(product_id)
        
        if product.company_id != company_id:
            flash('Producto no encontrado.', 'error')
            return redirect(url_for('inventory_list', company_id=company_id))
            
        if request.method == 'POST':
            product.name = request.form['name']
            product.sku = request.form.get('sku')
            product.description = request.form.get('description')
            product.cost_price = float(request.form.get('cost_price', 0))
            product.selling_price = float(request.form.get('selling_price', 0))
            product.min_stock_level = int(request.form.get('min_stock', 0))
            
            db.session.commit()
            flash(f'Producto "{product.name}" actualizado.', 'success')
            return redirect(url_for('inventory_list', company_id=company_id))
            
        return render_template('inventory/edit.html', company=company, product=product)

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
            # IVA Trasladado (Cobrado en Ventas)
            iva_collected = db.session.query(func.sum(Invoice.tax)).filter(
                Invoice.company_id == company_id,
                Invoice.type == 'I',  # Ingreso
                extract('month', Invoice.date) == month_num,
                extract('year', Invoice.date) == current_year
            ).scalar() or 0
            
            # IVA Acreditable (Pagado en Gastos)
            iva_deductible = db.session.query(func.sum(Invoice.tax)).filter(
                Invoice.company_id == company_id,
                Invoice.type == 'E',  # Egreso
                extract('month', Invoice.date) == month_num,
                extract('year', Invoice.date) == current_year
            ).scalar() or 0
            
            # Ingresos del mes (para ISR)
            month_income = db.session.query(func.sum(Invoice.subtotal)).filter(
                Invoice.company_id == company_id,
                Invoice.type == 'I',
                extract('month', Invoice.date) == month_num,
                extract('year', Invoice.date) == current_year
            ).scalar() or 0
            
            # Egresos del mes (para ISR)
            month_expense = db.session.query(func.sum(Invoice.subtotal)).filter(
                Invoice.company_id == company_id,
                Invoice.type == 'E',
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

    # Register CLI commands
    from cli import register_commands
    register_commands(app)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=False)
