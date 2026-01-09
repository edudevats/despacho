"""
Flask-WTF Forms
Forms with CSRF protection and validation.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, FloatField, IntegerField,
    TextAreaField, SelectField, DateField, DateTimeField, DecimalField, FileField, BooleanField
)
from wtforms.validators import (
    DataRequired, Email, Length, Optional, NumberRange, ValidationError, Regexp
)
from flask_wtf.file import FileAllowed
import re
from datetime import datetime


# Custom Validators
def validate_rfc(form, field):
    """Validate Mexican RFC format"""
    rfc = field.data.upper().strip()
    # RFC pattern: 3-4 letters + 6 digits (date) + 3 alphanumeric (homoclave)
    pattern_persona_moral = r'^[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}$'
    pattern_persona_fisica = r'^[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}$'
    
    if not (re.match(pattern_persona_moral, rfc) or re.match(pattern_persona_fisica, rfc)):
        raise ValidationError('RFC inválido. Debe tener 12 caracteres (persona moral) o 13 (persona física).')


# Authentication Forms
class LoginForm(FlaskForm):
    """Login form with CSRF protection"""
    username = StringField('Usuario', validators=[
        DataRequired(message='El usuario es requerido'),
        Length(min=3, max=64, message='El usuario debe tener entre 3 y 64 caracteres')
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message='La contraseña es requerida')
    ])
    remember_me = BooleanField('Recordarme')


class RegistrationForm(FlaskForm):
    """User registration form"""
    username = StringField('Usuario', validators=[
        DataRequired(),
        Length(min=3, max=64)
    ])
    email = StringField('Email', validators=[
        DataRequired(),
        Email(message='Email inválido')
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(),
        Length(min=8, message='La contraseña debe tener al menos 8 caracteres')
    ])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        DataRequired()
    ])
    
    def validate_confirm_password(self, field):
        if field.data != self.password.data:
            raise ValidationError('Las contraseñas no coinciden')


# Company Forms
class CompanyForm(FlaskForm):
    """Form for creating/editing companies"""
    rfc = StringField('RFC', validators=[
        DataRequired(message='El RFC es requerido'),
        Length(min=12, max=13, message='El RFC debe tener 12 o 13 caracteres'),
        validate_rfc
    ])
    name = StringField('Nombre o Razón Social', validators=[
        DataRequired(message='El nombre es requerido'),
        Length(max=128)
    ])
    postal_code = StringField('Código Postal', validators=[
        Optional(),
        Length(min=5, max=5, message='El CP debe tener 5 dígitos'),
        Regexp(r'^\d{5}$', message='Solo números')
    ])


class CompanyEditForm(FlaskForm):
    """Form for editing company details"""
    rfc = StringField('RFC', validators=[
        DataRequired(),
        Length(min=12, max=13),
        validate_rfc
    ])
    name = StringField('Nombre o Razón Social', validators=[
        DataRequired(),
        Length(max=128)
    ])
    postal_code = StringField('Código Postal', validators=[
        Optional(),
        Length(min=5, max=5, message='El CP debe tener 5 dígitos'),
        Regexp(r'^\d{5}$', message='Solo números')
    ])


# Sync Forms
class SyncForm(FlaskForm):
    """Form for SAT synchronization"""
    start_date = DateField('Fecha Inicio', validators=[DataRequired()])
    end_date = DateField('Fecha Fin', validators=[DataRequired()])
    fiel_cer = FileField('Archivo .cer (FIEL)', validators=[
        DataRequired(message='El archivo .cer es requerido'),
        FileAllowed(['cer'], 'Solo archivos .cer')
    ])
    fiel_key = FileField('Archivo .key (FIEL)', validators=[
        DataRequired(message='El archivo .key es requerido'),
        FileAllowed(['key'], 'Solo archivos .key')
    ])
    fiel_password = PasswordField('Contraseña FIEL', validators=[
        DataRequired(message='La contraseña es requerida')
    ])


# Tax Forms
class TaxPaymentForm(FlaskForm):
    """Form for recording tax payments"""
    month = SelectField('Mes', choices=[
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'),
        (4, 'Abril'), (5, 'Mayo'), (6, 'Junio'),
        (7, 'Julio'), (8, 'Agosto'), (9, 'Septiembre'),
        (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ], coerce=int, validators=[DataRequired()])
    year = IntegerField('Año', validators=[
        DataRequired(),
        NumberRange(min=2020, max=2030)
    ])
    tax_type = SelectField('Tipo de Impuesto', choices=[
        ('IVA', 'IVA'),
        ('ISR', 'ISR'),
        ('RETENCIONES', 'Retenciones')
    ], validators=[DataRequired()])
    amount = FloatField('Monto', validators=[
        DataRequired(),
        NumberRange(min=0, message='El monto debe ser positivo')
    ])
    notes = TextAreaField('Notas', validators=[Optional(), Length(max=500)])


# Category Forms
class CategoryForm(FlaskForm):
    """Form for creating/editing categories"""
    name = StringField('Nombre', validators=[
        DataRequired(),
        Length(max=100)
    ])
    type = SelectField('Tipo', choices=[
        ('INCOME', 'Ingreso'),
        ('EXPENSE', 'Egreso')
    ], validators=[DataRequired()])
    description = TextAreaField('Descripción', validators=[
        Optional(),
        Length(max=256)
    ])
    color = StringField('Color', validators=[
        Optional(),
        Length(max=7)
    ], default='#6c757d')


# Supplier Forms
class SupplierForm(FlaskForm):
    """Form for editing supplier information"""
    commercial_name = StringField('Nombre Comercial', validators=[
        Optional(),
        Length(max=256)
    ])
    email = StringField('Email', validators=[
        Optional(),
        Email(message='Email inválido')
    ])
    phone = StringField('Teléfono', validators=[
        Optional(),
        Length(max=20)
    ])
    address = TextAreaField('Dirección', validators=[
        Optional(),
        Length(max=500)
    ])
    notes = TextAreaField('Notas', validators=[
        Optional(),
        Length(max=1000)
    ])
    tags = StringField('Etiquetas (separadas por coma)', validators=[
        Optional(),
        Length(max=256)
    ])
    is_favorite = BooleanField('Favorito')


# Search Forms
class InvoiceSearchForm(FlaskForm):
    """Advanced invoice search form"""
    q = StringField('Buscar', validators=[Optional()])
    supplier_id = SelectField('Proveedor', coerce=int, validators=[Optional()])
    category_id = SelectField('Categoría', coerce=int, validators=[Optional()])
    date_from = DateField('Desde', validators=[Optional()])
    date_to = DateField('Hasta', validators=[Optional()])
    min_amount = FloatField('Monto mínimo', validators=[Optional()])
    max_amount = FloatField('Monto máximo', validators=[Optional()])

# Inventory Forms
class ProductForm(FlaskForm):
    """Form for creating/editing products"""
    name = StringField('Nombre del Producto', validators=[
        DataRequired(),
        Length(max=200)
    ])
    sku = StringField('SKU / Código', validators=[
        Optional(),
        Length(max=50)
    ])
    description = TextAreaField('Descripción', validators=[Optional()])
    
    cost_price = FloatField('Costo Real', validators=[
        NumberRange(min=0, message='El costo debe ser positivo'),
        Optional()
    ], default=0.0)
    
    selling_price = FloatField('Precio Venta', validators=[
        NumberRange(min=0, message='El precio debe ser positivo'),
        Optional()
    ], default=0.0)
    
    initial_stock = IntegerField('Stock Inicial', validators=[
        Optional(),
        NumberRange(min=0)
    ])
    
    min_stock_level = IntegerField('Stock Mínimo', validators=[
        Optional(),
        NumberRange(min=0)
    ])
    
    # COFEPRIS Fields
    sanitary_registration = StringField('Registro Sanitario', validators=[
        Optional(),
        Length(max=100)
    ])
    is_controlled = BooleanField('Medicamento Controlado')
    
    active_ingredient = StringField('Principio Activo', validators=[
        Optional(),
        Length(max=200)
    ])
    presentation = StringField('Presentación', validators=[
        Optional(),
        Length(max=100)
    ])
    therapeutic_group = StringField('Grupo Terapéutico', validators=[
        Optional(),
        Length(max=100)
    ])
    unit_measure = SelectField('Unidad de Medida', choices=[
        ('PZA', 'Pieza'),
        ('CAJA', 'Caja'),
        ('PAQ', 'Paquete'),
        ('KIT', 'Kit'),
        ('LITRO', 'Litro'),
        ('METRO', 'Metro')
    ], default='PZA')


class BatchForm(FlaskForm):
    """Form for adding a new batch"""
    batch_number = StringField('Número de Lote', validators=[
        DataRequired(),
        Length(max=100)
    ])
    expiration_date = DateField('Fecha de Caducidad', validators=[DataRequired()])
    quantity = IntegerField('Cantidad', validators=[
        DataRequired(),
        NumberRange(min=1, message='La cantidad debe ser mayor a 0')
    ])
    acquisition_date = DateField('Fecha de Adquisición', default=datetime.utcnow)


# Facturación Forms
class FinkokCredentialsForm(FlaskForm):
    """Form for configuring Finkok credentials"""
    username = StringField('Usuario de Finkok', validators=[
        DataRequired(message='El usuario es requerido'),
        Length(max=120)
    ])
    password = PasswordField('Contraseña/Token', validators=[
        DataRequired(message='La contraseña es requerida')
    ])
    environment = SelectField('Ambiente', choices=[
        ('TEST', 'Pruebas'),
        ('PRODUCTION', 'Producción')
    ], validators=[DataRequired()], default='TEST')


class TimbrarFacturaForm(FlaskForm):
    """Form for stamping invoices"""
    xml_file = FileField('Archivo XML', validators=[
        DataRequired(message='El archivo XML es requerido'),
        FileAllowed(['xml'], 'Solo archivos XML')
    ])
    accept = SelectField('Formato de salida', choices=[
        ('XML_PDF', 'XML y PDF'),
        ('XML', 'Solo XML'),
        ('PDF', 'Solo PDF')
    ], validators=[DataRequired()], default='XML_PDF')


class ConsultarEstadoForm(FlaskForm):
    """Form for checking CFDI status"""
    xml_file = FileField('Archivo XML del CFDI', validators=[
        Optional(),
        FileAllowed(['xml'], 'Solo archivos XML')
    ])
    # Alternative: manual input
    uuid = StringField('UUID (alternativo)', validators=[
        Optional(),
        Length(min=36, max=36, message='UUID debe tener 36 caracteres')
    ])
    rfc_emisor = StringField('RFC Emisor', validators=[
        Optional(),
        validate_rfc
    ])
    rfc_receptor = StringField('RFC Receptor', validators=[
        Optional(),
        validate_rfc
    ])
    total = FloatField('Total', validators=[
        Optional(),
        NumberRange(min=0)
    ])


class Lista69BForm(FlaskForm):
    """Form for checking 69B list"""
    rfc = StringField('RFC a Consultar', validators=[
        DataRequired(message='El RFC es requerido'),
        Length(min=12, max=13, message='El RFC debe tener 12 o 13 caracteres'),
        validate_rfc
    ])


# Generador de CFDI Forms
class CFDIComprobanteForm(FlaskForm):
    """Form para datos generales del comprobante y FIEL"""
    # FIEL (como en sincronización)
    fiel_cer = FileField('Certificado FIEL (.cer)', validators=[
        DataRequired(message='El certificado FIEL es requerido'),
        FileAllowed(['cer'], 'Solo archivos .cer')
    ], render_kw={'accept': '.cer'})
    fiel_key = FileField('Llave Privada FIEL (.key)', validators=[
        DataRequired(message='La llave privada FIEL es requerida'),
        FileAllowed(['key'], 'Solo archivos .key')
    ], render_kw={'accept': '.key'})
    fiel_password = PasswordField('Contraseña FIEL', validators=[
        DataRequired(message='La contraseña FIEL es requerida')
    ])
    
    # Datos del comprobante
    serie = StringField('Serie', validators=[Optional(), Length(max=25)])
    folio = StringField('Folio', validators=[Optional(), Length(max=40)])
    fecha = DateTimeField('Fecha de Emisión', format='%Y-%m-%d %H:%M:%S', 
                         default=datetime.utcnow, validators=[DataRequired()])
    lugar_expedicion = StringField('Lugar de Expedición (CP)', validators=[
        DataRequired(message='El código postal de expedición es requerido'),
        Length(min=5, max=5, message='Debe ser un código postal de 5 dígitos'),
        Regexp(r'^\d{5}$', message='Solo números')
    ])
    forma_pago = SelectField('Forma de Pago', choices=[
        ('01', '01 - Efectivo'),
        ('02', '02 - Cheque nominativo'),
        ('03', '03 - Transferencia electrónica'),
        ('04', '04 - Tarjeta de crédito'),
        ('28', '28 - Tarjeta de débito'),
        ('99', '99 - Por definir')
    ], validators=[DataRequired()], default='01')
    metodo_pago = SelectField('Método de Pago', choices=[
        ('PUE', 'PUE - Pago en una sola exhibición'),
        ('PPD', 'PPD - Pago en parcialidades o diferido')
    ], validators=[DataRequired()], default='PUE')


class CFDIReceptorForm(FlaskForm):
    """Form para datos del receptor"""
    receptor_rfc = StringField('RFC del Receptor', validators=[
        DataRequired(message='El RFC del receptor es requerido'),
        Length(min=12, max=13, message='El RFC debe tener 12 o 13 caracteres'),
        validate_rfc
    ])
    receptor_nombre = StringField('Nombre/Razón Social', validators=[
        DataRequired(message='El nombre es requerido'),
        Length(max=256)
    ])
    receptor_cp = StringField('Código Postal', validators=[
        DataRequired(message='El código postal es requerido'),
        Length(min=5, max=5, message='Debe ser de 5 dígitos'),
        Regexp(r'^\d{5}$', message='Solo números')
    ])
    receptor_uso_cfdi = SelectField('Uso del CFDI', choices=[
        ('G01', 'G01 - Adquisición de mercancías'),
        ('G02', 'G02 - Devoluciones, descuentos o bonificaciones'),
        ('G03', 'G03 - Gastos en general'),
        ('I01', 'I01 - Construcciones'),
        ('I02', 'I02 - Mobiliario y equipo de oficina por inversiones'),
        ('I03', 'I03 - Equipo de transporte'),
        ('I04', 'I04 - Equipo de cómputo y accesorios'),
        ('I05', 'I05 - Dados, troqueles, moldes, matrices y herramental'),
        ('I06', 'I06 - Comunicaciones telefónicas'),
        ('I07', 'I07 - Comunicaciones satelitales'),
        ('I08', 'I08 - Otra maquinaria y equipo'),
        ('D01', 'D01 - Honorarios médicos, dentales y gastos hospitalarios'),
        ('D02', 'D02 - Gastos médicos por incapacidad o discapacidad'),
        ('D03', 'D03 - Gastos funerales'),
        ('D04', 'D04 - Donativos'),
        ('D05', 'D05 - Intereses reales efectivamente pagados por créditos hipotecarios'),
        ('D06', 'D06 - Aportaciones voluntarias al SAR'),
        ('D07', 'D07 - Primas por seguros de gastos médicos'),
        ('D08', 'D08 - Gastos de transportación escolar obligatoria'),
        ('D09', 'D09 - Depósitos en cuentas para el ahorro, primas que tengan como base planes de pensiones'),
        ('D10', 'D10 - Pagos por servicios educativos (colegiaturas)'),
        ('S01', 'S01 - Sin efectos fiscales'),
        ('CP01', 'CP01 - Pagos'),
        ('CN01', 'CN01 - Nómina')
    ], validators=[DataRequired()], default='G03')
    receptor_regimen = SelectField('Régimen Fiscal', choices=[
        ('601', '601 - General de Ley Personas Morales'),
        ('603', '603 - Personas Morales con Fines no Lucrativos'),
        ('605', '605 - Sueldos y Salarios e Ingresos Asimilados a Salarios'),
        ('606', '606 - Arrendamiento'),
        ('608', '608 - Demás ingresos'),
        ('610', '610 - Residentes en el Extranjero sin Establecimiento Permanente en México'),
        ('611', '611 - Ingresos por Dividendos (socios y accionistas)'),
        ('612', '612 - Personas Físicas con Actividades Empresariales y Profesionales'),
        ('614', '614 - Ingresos por intereses'),
        ('615', '615 - Régimen de los ingresos por obtención de premios'),
        ('616', '616 - Sin obligaciones fiscales'),
        ('620', '620 - Sociedades Cooperativas de Producción que optan por diferir sus ingresos'),
        ('621', '621 - Incorporación Fiscal'),
        ('622', '622 - Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras'),
        ('623', '623 - Opcional para Grupos de Sociedades'),
        ('624', '624 - Coordinados'),
        ('625', '625 - Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas'),
        ('626', '626 - Régimen Simplificado de Confianza')
    ], validators=[DataRequired()], default='601')


class CFDIConceptoForm(FlaskForm):
    """Form para agregar conceptos/productos a la factura"""
    clave_prod_serv = StringField('Clave Producto/Servicio', validators=[
        DataRequired(message='La clave es requerida'),
        Length(min=8, max=8, message='Debe ser de 8 dígitos')
    ], default='01010101')
    no_identificacion = StringField('No. Identificación', validators=[Optional(), Length(max=100)])
    cantidad = DecimalField('Cantidad', validators=[
        DataRequired(message='La cantidad es requerida'),
        NumberRange(min=0.01, message='Debe ser mayor a 0')
    ], default=1)
    clave_unidad = StringField('Clave Unidad', validators=[
        DataRequired(message='La clave de unidad es requerida'),
        Length(max=20)
    ], default='E48')
    unidad = StringField('Unidad', validators=[Optional(), Length(max=20)], default='Servicio')
    descripcion = TextAreaField('Descripción', validators=[
        DataRequired(message='La descripción es requerida'),
        Length(max=1000)
    ])
    valor_unitario = DecimalField('Valor Unitario', validators=[
        DataRequired(message='El valor unitario es requerido'),
        NumberRange(min=0.01, message='Debe ser mayor a 0')
    ], places=2)
    descuento = DecimalField('Descuento', validators=[
        Optional(),
        NumberRange(min=0, message='No puede ser negativo')
    ], default=0, places=2)
    tasa_iva = SelectField('Tasa de IVA', choices=[
        ('0.16', '16%'),
        ('0.08', '8%'),
        ('0.00', '0% (Exento)')
    ], validators=[DataRequired()], default='0.16')

