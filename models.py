from flask_login import UserMixin
from datetime import datetime
from extensions import db


class User(UserMixin, db.Model):
    """User model for authentication and authorization."""
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256))  # Larger for modern hash algorithms

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)  # Admin can manage users and access all

    # Relationships
    company_access = db.relationship('UserCompanyAccess', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.username}>'

    def can_access_company(self, company_id):
        """Check if user can access a specific company"""
        if self.is_admin:
            return True
        return any(access.company_id == company_id for access in self.company_access)

    def get_company_permissions(self, company_id):
        """Get permissions for a specific company"""
        if self.is_admin:
            # Admin has all permissions
            return {
                'dashboard': True, 'sync': True, 'inventory': True,
                'invoices': True, 'ppd': True, 'taxes': True,
                'sales': True, 'facturacion': True
            }
        for access in self.company_access:
            if access.company_id == company_id:
                return {
                    'dashboard': access.perm_dashboard,
                    'sync': access.perm_sync,
                    'inventory': access.perm_inventory,
                    'invoices': access.perm_invoices,
                    'ppd': access.perm_ppd,
                    'taxes': access.perm_taxes,
                    'sales': access.perm_sales,
                    'facturacion': access.perm_facturacion
                }
        return {}

    def get_accessible_companies(self):
        """Get list of companies user can access"""
        if self.is_admin:
            return Company.query.all()
        return [access.company for access in self.company_access]


class UserCompanyAccess(db.Model):
    """Controls which companies a user can access and what permissions they have"""
    __tablename__ = 'user_company_access'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    # Menu permissions
    perm_dashboard = db.Column(db.Boolean, default=True)
    perm_sync = db.Column(db.Boolean, default=False)
    perm_inventory = db.Column(db.Boolean, default=False)
    perm_invoices = db.Column(db.Boolean, default=False)
    perm_ppd = db.Column(db.Boolean, default=False)
    perm_taxes = db.Column(db.Boolean, default=False)
    perm_sales = db.Column(db.Boolean, default=False)
    perm_facturacion = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', back_populates='company_access')
    company = db.relationship('Company', backref=db.backref('user_access', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'company_id', name='unique_user_company'),
    )

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfc = db.Column(db.String(13), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    postal_code = db.Column(db.String(5), nullable=True) # Código Postal (Lugar Expedición)
    logo_path = db.Column(db.String(512), nullable=True)  # Path to company logo
    fiel_cer_path = db.Column(db.String(256), nullable=True)
    fiel_key_path = db.Column(db.String(256), nullable=True)
    fiel_password_enc = db.Column(db.String(256), nullable=True) # Encrypted password
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    """
    Categorías para clasificar ingresos y egresos
    """
    __tablename__ = 'category'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'INCOME' o 'EXPENSE'
    description = db.Column(db.Text)
    is_default = db.Column(db.Boolean, default=False)  # Categoría por defecto del sistema
    active = db.Column(db.Boolean, default=True)
    color = db.Column(db.String(7), default='#6c757d')  # Hex color para gráficas
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    company = db.relationship('Company', backref=db.backref('categories', lazy=True))
    movements = db.relationship('Movement', backref='category', lazy=True)
    
    def __repr__(self):
        return f'<Category {self.name} - {self.type}>'

class Supplier(db.Model):
    """
    Proveedores (emisores de facturas recibidas y proveedores de medicamentos)
    Se genera automáticamente desde las facturas o manualmente
    """
    __tablename__ = 'supplier'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    rfc = db.Column(db.String(13), nullable=False, index=True)
    business_name = db.Column(db.String(256))  # Razón social
    commercial_name = db.Column(db.String(256))  # Nombre comercial (opcional)

    # Datos de contacto (opcional, para agregar manualmente)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)

    # Campos adicionales para proveedores de medicamentos
    contact_name = db.Column(db.String(150), nullable=True)  # Nombre de contacto
    payment_terms = db.Column(db.String(200), nullable=True)  # Condiciones de pago (ej: "30 días", "Contado")
    is_medication_supplier = db.Column(db.Boolean, default=False)  # Es proveedor de medicamentos
    sanitary_registration = db.Column(db.String(100), nullable=True)  # Registro Sanitario del proveedor

    # Estadísticas auto-calculadas
    total_invoiced = db.Column(db.Float, default=0)  # Total facturado
    invoice_count = db.Column(db.Integer, default=0)  # Cantidad de facturas
    last_invoice_date = db.Column(db.DateTime)
    first_invoice_date = db.Column(db.DateTime)

    # Notas y categorización
    notes = db.Column(db.Text)
    tags = db.Column(db.String(256))  # Tags separados por coma
    is_favorite = db.Column(db.Boolean, default=False)

    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship('Company', backref=db.backref('suppliers', lazy=True))
    invoices = db.relationship('Invoice', backref='supplier', lazy=True,
                              foreign_keys='Invoice.supplier_id')

    __table_args__ = (
        db.UniqueConstraint('company_id', 'rfc', name='unique_supplier_per_company'),
    )

    def __repr__(self):
        return f'<Supplier {self.business_name} - {self.rfc}>'

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)  # Solo para facturas recibidas
    
    date = db.Column(db.DateTime, nullable=False)
    total = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    tax = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(1)) # I=Ingreso, E=Egreso, P=Pago
    issuer_rfc = db.Column(db.String(13))
    issuer_name = db.Column(db.String(256))  # Nombre del emisor
    receiver_rfc = db.Column(db.String(13))
    receiver_name = db.Column(db.String(256))  # Nombre del receptor
    forma_pago = db.Column(db.String(3))  # 01=Efectivo, 03=Transferencia, 04=Tarjeta, etc.
    metodo_pago = db.Column(db.String(3))  # PUE=Una exhibición, PPD=Diferido
    uso_cfdi = db.Column(db.String(4))  # G01, G03, D01, etc.
    descripcion = db.Column(db.Text)  # Descripción del concepto
    xml_content = db.Column(db.Text) # Store full XML if needed
    
    # Campos adicionales para CFDI 4.0 y Global
    periodicity = db.Column(db.String(5))   # 01, 02, ...
    months = db.Column(db.String(5))        # 01, 02, ...
    fiscal_year = db.Column(db.String(5))   # 2023, 2024
    
    payment_terms = db.Column(db.Text)      # CondicionesDePago
    currency = db.Column(db.String(5))      # Moneda
    exchange_rate = db.Column(db.Float)     # TipoCambio
    exportation = db.Column(db.String(5))   # Exportacion
    version = db.Column(db.String(5))       # 3.3, 4.0
    
    # --- Datos del Nodo: Comprobante ---
    serie = db.Column(db.String(25))
    folio = db.Column(db.String(40))
    lugar_expedicion = db.Column(db.String(10)) # C.P.
    no_certificado = db.Column(db.String(20))   # Del emisor
    sello = db.Column(db.Text)                  # Sello digital del emisor
    certificado = db.Column(db.Text)            # Certificado codificado (opcional)

    # --- Datos del Nodo: Emisor ---
    regimen_fiscal_emisor = db.Column(db.String(10)) # Clave régimen

    # --- Datos del Nodo: Receptor ---
    regimen_fiscal_receptor = db.Column(db.String(10))
    domicilio_fiscal_receptor = db.Column(db.String(10)) # C.P.

    # --- Datos del Nodo: TimbreFiscalDigital (Complemento) ---
    fecha_timbrado = db.Column(db.DateTime)
    rfc_prov_certif = db.Column(db.String(20))
    sello_sat = db.Column(db.Text)
    no_certificado_sat = db.Column(db.String(20))
    
    # Campos para acreditación de facturas PPD (Pago en Parcialidades o Diferido)
    ppd_acreditado = db.Column(db.Boolean, default=False)  # Si la factura PPD fue acreditada
    ppd_fecha_acreditacion = db.Column(db.DateTime, nullable=True)  # Cuándo se acreditó
    ppd_mes_acreditado = db.Column(db.Integer, nullable=True)  # Mes al que se acredita (1-12)
    ppd_anio_acreditado = db.Column(db.Integer, nullable=True)  # Año al que se acredita

    company = db.relationship('Company', backref=db.backref('invoices', lazy=True))

class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10)) # INCOME / EXPENSE
    description = db.Column(db.String(256))
    date = db.Column(db.DateTime, nullable=False)
    
    # Fuente del movimiento
    source = db.Column(db.String(20), default='invoice')  # 'invoice' o 'manual'
    
    # Notas adicionales
    notes = db.Column(db.Text)
    
    invoice = db.relationship('Invoice', backref=db.backref('movement', uselist=False))
    company = db.relationship('Company', backref=db.backref('movements', lazy=True))

class TaxPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    period_month = db.Column(db.Integer, nullable=False)
    period_year = db.Column(db.Integer, nullable=False)

    tax_type = db.Column(db.String(20), nullable=False)  # 'IVA', 'ISR', 'RETENCIONES'
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)

    status = db.Column(db.String(20), default='PAID')  # PAID, PENDING
    notes = db.Column(db.Text)

    company = db.relationship('Company', backref=db.backref('tax_payments', lazy=True))


class Laboratory(db.Model):
    """
    Laboratorios (fabricantes de medicamentos)
    """
    __tablename__ = 'laboratory'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    sanitary_registration = db.Column(db.String(100), nullable=True)  # Registro Sanitario del laboratorio
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship('Company', backref=db.backref('laboratories', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('company_id', 'name', name='unique_laboratory_per_company'),
    )

    def __repr__(self):
        return f'<Laboratory {self.name}>'


class Product(db.Model):
    """
    Producto/Medicamento para inventario
    """
    __tablename__ = 'product'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    sku = db.Column(db.String(50), nullable=True)  # Código interno/barras
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    cost_price = db.Column(db.Float, default=0.0)  # Costo real (para valuación inventario)
    selling_price = db.Column(db.Float, default=0.0)  # Precio venta manual (override)
    profit_margin = db.Column(db.Float, default=0.0)  # Porcentaje de ganancia individual

    current_stock = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=0)

    # Relaciones con laboratorio y proveedor
    laboratory_id = db.Column(db.Integer, db.ForeignKey('laboratory.id'), nullable=True)
    preferred_supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)

    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Campos específicos para COFEPRIS
    sanitary_registration = db.Column(db.String(100), nullable=True)  # Registro Sanitario
    is_controlled = db.Column(db.Boolean, default=False)  # Si es medicamento controlado (Fracción I, II, III)
    active_ingredient = db.Column(db.String(200), nullable=True)  # Principio activo
    presentation = db.Column(db.String(100), nullable=True)  # Presentación (e.g., Tabletas, Jarabe)
    therapeutic_group = db.Column(db.String(100), nullable=True)  # Grupo Terapéutico
    unit_measure = db.Column(db.String(20), default='PZA')  # PZA, CAJA, etc.

    company = db.relationship('Company', backref=db.backref('products', lazy=True))
    laboratory = db.relationship('Laboratory', backref=db.backref('products', lazy=True))
    preferred_supplier = db.relationship('Supplier', backref=db.backref('preferred_products', lazy=True))

    @property
    def calculated_selling_price(self):
        """Calcula el precio de venta basado en costo y margen de ganancia"""
        if self.selling_price and self.selling_price > 0:
            return self.selling_price  # Override manual
        if self.cost_price and self.profit_margin:
            return self.cost_price * (1 + self.profit_margin / 100)
        return self.cost_price or 0.0

    def __repr__(self):
        return f'<Product {self.name}>'

class ProductBatch(db.Model):
    """
    Lotes de productos (para manejo de caducidades COFEPRIS)
    """
    __tablename__ = 'product_batch'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    
    batch_number = db.Column(db.String(100), nullable=False) # Número de Lote
    expiration_date = db.Column(db.Date, nullable=False) # Fecha de Caducidad
    
    initial_stock = db.Column(db.Integer, default=0)
    current_stock = db.Column(db.Integer, default=0)
    
    acquisition_date = db.Column(db.Date, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True) # Se desactiva si stock es 0 o caducado
    
    product = db.relationship('Product', backref=db.backref('batches', lazy=True, order_by='ProductBatch.expiration_date.asc()'))

    def __repr__(self):
        return f'<Batch {self.batch_number} - Exp: {self.expiration_date}>'

class InventoryTransaction(db.Model):
    """
    Historial de movimientos de inventario
    """
    __tablename__ = 'inventory_transaction'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('product_batch.id'), nullable=True) # Link to specific batch
    
    type = db.Column(db.String(20), nullable=False) # 'IN', 'OUT', 'ADJUSTMENT'
    quantity = db.Column(db.Integer, nullable=False) # Cantidad movida (positiva o negativa según lógica, aqui guardamos valor absoluto y el tipo define)
    
    previous_stock = db.Column(db.Integer, nullable=False)
    new_stock = db.Column(db.Integer, nullable=False)
    
    date = db.Column(db.DateTime, default=datetime.utcnow)
    reference = db.Column(db.String(100)) # ID Factura, Orden, etc.
    notes = db.Column(db.Text)

    # Campos para dispensa de medicamentos controlados (COFEPRIS)
    doctor_name = db.Column(db.String(150), nullable=True)
    doctor_license = db.Column(db.String(50), nullable=True) # Cédula Profesional
    patient_name = db.Column(db.String(150), nullable=True)
    
    product = db.relationship('Product', backref=db.backref('transactions', lazy=True, order_by='InventoryTransaction.date.desc()'))
    batch = db.relationship('ProductBatch', backref=db.backref('transactions', lazy=True))


class FinkokCredentials(db.Model):
    """
    Credenciales de Finkok para timbrado de facturas por empresa.
    La contraseña se almacena cifrada.
    """
    __tablename__ = 'finkok_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False, unique=True)
    
    username = db.Column(db.String(120), nullable=False)
    password_enc = db.Column(db.String(256), nullable=False)  # Encrypted password/token
    environment = db.Column(db.String(10), default='TEST')  # TEST o PRODUCTION
    
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = db.relationship('Company', backref=db.backref('finkok_credentials', uselist=False))
    
    def __repr__(self):
        return f'<FinkokCredentials {self.username} - {self.environment}>'


class InvoiceFolioCounter(db.Model):
    """
    Contador de folios por compañía y serie.
    Permite rastrear el último folio usado para cada serie de facturas.
    """
    __tablename__ = 'invoice_folio_counter'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    serie = db.Column(db.String(25), nullable=False, default='A')  # Serie de factura
    current_folio = db.Column(db.Integer, default=0)  # Último folio usado
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = db.relationship('Company', backref=db.backref('folio_counters', lazy=True))
    
    __table_args__ = (
        db.UniqueConstraint('company_id', 'serie', name='unique_folio_per_company_serie'),
    )
    
    def __repr__(self):
        return f'<InvoiceFolioCounter Company:{self.company_id} Serie:{self.serie} Folio:{self.current_folio}>'


class Customer(db.Model):
    """
    Clientes/Receptores de facturas.
    Almacena datos básicos de clientes para facilitar la emisión de facturas.
    """
    __tablename__ = 'customer'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    rfc = db.Column(db.String(13), nullable=False, index=True)
    nombre = db.Column(db.String(256), nullable=False)
    codigo_postal = db.Column(db.String(5), nullable=False)
    regimen_fiscal = db.Column(db.String(10), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = db.relationship('Company', backref=db.backref('customers', lazy=True))
    
    __table_args__ = (
        db.UniqueConstraint('company_id', 'rfc', name='unique_customer_per_company'),
    )
    
    def __repr__(self):
        return f'<Customer {self.nombre} - {self.rfc}>'


class Service(db.Model):
    """
    Servicios médicos para facturación
    """
    __tablename__ = 'service'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, default=0.0)
    sat_key = db.Column(db.String(10), default='01010101')  # Clave de producto/servicio SAT
    sat_unit_key = db.Column(db.String(10), default='E48')  # Clave de unidad SAT (E48 = Unidad de servicio)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship('Company', backref=db.backref('services', lazy=True))

    def __repr__(self):
        return f'<Service {self.name}>'


class PurchaseOrder(db.Model):
    """
    Órdenes de compra (cabecera)
    """
    __tablename__ = 'purchase_order'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)

    # Estados: DRAFT (borrador), SENT (enviada), IN_REVIEW (recepción), COMPLETED (cerrada)
    status = db.Column(db.String(20), default='DRAFT')
    estimated_total = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)  # Cuando se envió
    received_at = db.Column(db.DateTime, nullable=True)  # Cuando se recibió físicamente
    completed_at = db.Column(db.DateTime, nullable=True)  # Cuando se cerró

    company = db.relationship('Company', backref=db.backref('purchase_orders', lazy=True))
    supplier = db.relationship('Supplier', backref=db.backref('purchase_orders', lazy=True))

    def __repr__(self):
        return f'<PurchaseOrder #{self.id} - {self.status}>'


class PurchaseOrderDetail(db.Model):
    """
    Detalles de órdenes de compra (renglones)
    """
    __tablename__ = 'purchase_order_detail'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('purchase_order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)

    quantity_requested = db.Column(db.Integer, default=0)  # Cantidad solicitada (Fase 1)
    quantity_received = db.Column(db.Integer, default=0)  # Cantidad recibida (Fase 2)
    unit_cost = db.Column(db.Float, default=0.0)  # Costo unitario (solo referencia)

    # Batch/Lot information for COFEPRIS compliance
    batch_number = db.Column(db.String(50), nullable=True)  # Numero de lote
    expiration_date = db.Column(db.Date, nullable=True)  # Fecha de caducidad

    order = db.relationship('PurchaseOrder', backref=db.backref('details', lazy=True, cascade='all, delete-orphan'))
    product = db.relationship('Product', backref=db.backref('order_details', lazy=True))

    @property
    def difference(self):
        """Diferencia entre solicitado y recibido"""
        return self.quantity_received - self.quantity_requested

    def __repr__(self):
        return f'<PurchaseOrderDetail Order:{self.order_id} Product:{self.product_id}>'


class ExitOrder(db.Model):
    """
    Ordenes de salida - registro de entregas de medicamentos/productos
    """
    __tablename__ = 'exit_order'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    # Destinatario
    recipient_name = db.Column(db.String(200), nullable=False)  # Nombre del paciente/departamento
    recipient_type = db.Column(db.String(50), default='PATIENT')  # PATIENT, DEPARTMENT, OTHER
    recipient_id = db.Column(db.String(50), nullable=True)  # ID del paciente, numero de expediente, etc.

    # Estado y fechas
    status = db.Column(db.String(20), default='DRAFT')  # DRAFT, COMPLETED, CANCELLED
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Relationships
    company = db.relationship('Company', backref=db.backref('exit_orders', lazy=True))
    created_by = db.relationship('User', backref=db.backref('exit_orders', lazy=True))

    @property
    def total_items(self):
        """Total de productos en la orden"""
        return sum(d.quantity for d in self.details)

    def __repr__(self):
        return f'<ExitOrder #{self.id} - {self.recipient_name}>'


class ExitOrderDetail(db.Model):
    """
    Detalles de ordenes de salida (productos entregados)
    """
    __tablename__ = 'exit_order_detail'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('exit_order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('product_batch.id'), nullable=True)  # Lote especifico

    quantity = db.Column(db.Integer, default=1)  # Cantidad entregada

    # Relationships
    order = db.relationship('ExitOrder', backref=db.backref('details', lazy=True, cascade='all, delete-orphan'))
    product = db.relationship('Product', backref=db.backref('exit_details', lazy=True))
    batch = db.relationship('ProductBatch', backref=db.backref('exit_details', lazy=True))

    def __repr__(self):
        return f'<ExitOrderDetail Order:{self.order_id} Product:{self.product_id}>'


class InvoiceTemplate(db.Model):
    """
    Plantillas de factura para procedimientos médicos
    """
    __tablename__ = 'invoice_template'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship('Company', backref=db.backref('invoice_templates', lazy=True))

    def __repr__(self):
        return f'<InvoiceTemplate {self.name}>'


class InvoiceTemplateItem(db.Model):
    """
    Items de plantillas de factura (productos o servicios)
    """
    __tablename__ = 'invoice_template_item'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('invoice_template.id'), nullable=False)

    # Tipo de item: 'PRODUCT' o 'SERVICE'
    item_type = db.Column(db.String(20), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=True)
    quantity = db.Column(db.Float, default=1.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    template = db.relationship('InvoiceTemplate', backref=db.backref('items', lazy=True, cascade='all, delete-orphan'))
    product = db.relationship('Product', backref=db.backref('template_items', lazy=True))
    service = db.relationship('Service', backref=db.backref('template_items', lazy=True))

    @property
    def item_name(self):
        """Nombre del item (producto o servicio)"""
        if self.item_type == 'PRODUCT' and self.product:
            return self.product.name
        elif self.item_type == 'SERVICE' and self.service:
            return self.service.name
        return 'Sin nombre'

    @property
    def item_price(self):
        """Precio del item (producto calculado o servicio)"""
        if self.item_type == 'PRODUCT' and self.product:
            return self.product.calculated_selling_price
        elif self.item_type == 'SERVICE' and self.service:
            return self.service.price
        return 0.0

    def __repr__(self):
        return f'<InvoiceTemplateItem {self.item_type} Template:{self.template_id}>'


# Late import to avoid circular dependency if needed, or put at top if safe.
# Assuming utils package exists.
from utils.cfdi_catalog import get_cfdi_usage_info

# Add property to Invoice
@property
def usage_info(self):
    return get_cfdi_usage_info(self.uso_cfdi)

Invoice.usage_info = usage_info
