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
    
    def __repr__(self):
        return f'<User {self.username}>'

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rfc = db.Column(db.String(13), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
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
    Proveedores (emisores de facturas recibidas)
    Se genera automáticamente desde las facturas
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
    
    tax_type = db.Column(db.String(20), nullable=False) # 'IVA', 'ISR', 'RETENCIONES'
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    status = db.Column(db.String(20), default='PAID') # PAID, PENDING
    notes = db.Column(db.Text)
    
    company = db.relationship('Company', backref=db.backref('tax_payments', lazy=True))

class Product(db.Model):
    """
    Producto para inventario
    """
    __tablename__ = 'product'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    
    sku = db.Column(db.String(50), nullable=True) # Código interno/barras
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    cost_price = db.Column(db.Float, default=0.0) # Costo real (para valuación inventario)
    selling_price = db.Column(db.Float, default=0.0) # Precio venta al público
    
    current_stock = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=0)
    
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Campos específicos para COFEPRIS
    sanitary_registration = db.Column(db.String(100), nullable=True) # Registro Sanitario
    is_controlled = db.Column(db.Boolean, default=False) # Si es medicamento controlado (Fracción I, II, III)
    active_ingredient = db.Column(db.String(200), nullable=True) # Principio activo
    presentation = db.Column(db.String(100), nullable=True) # Presentación (e.g., Tabletas, Jarabe)
    therapeutic_group = db.Column(db.String(100), nullable=True) # Grupo Terapéutico
    unit_measure = db.Column(db.String(20), default='PZA') # PZA, CAJA, etc.
    
    company = db.relationship('Company', backref=db.backref('products', lazy=True))
    
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


# Late import to avoid circular dependency if needed, or put at top if safe.
# Assuming utils package exists.
from utils.cfdi_catalog import get_cfdi_usage_info

# Add property to Invoice
@property
def usage_info(self):
    return get_cfdi_usage_info(self.uso_cfdi)

Invoice.usage_info = usage_info
