"""
Flask-WTF Forms
Forms with CSRF protection and validation.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, FloatField, IntegerField,
    TextAreaField, SelectField, DateField, FileField, BooleanField
)
from wtforms.validators import (
    DataRequired, Email, Length, Optional, NumberRange, ValidationError
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

