"""
Formularios de Movimientos
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import SelectField, DateField, DecimalField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Optional
from datetime import date


class IngresoForm(FlaskForm):
    """Formulario para registrar ingresos"""
    categoria_id = SelectField('Categoría', coerce=int, validators=[DataRequired()])
    fecha = DateField('Fecha', default=date.today, validators=[DataRequired()])
    monto = DecimalField('Monto', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    metodo_pago = SelectField('Método de Pago', choices=[
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta')
    ], validators=[DataRequired()])
    notas = TextAreaField('Notas', validators=[Optional()])


class EgresoForm(FlaskForm):
    """Formulario para registrar egresos"""
    categoria_id = SelectField('Categoría', coerce=int, validators=[DataRequired()])
    fecha = DateField('Fecha', default=date.today, validators=[DataRequired()])
    monto = DecimalField('Monto', places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    metodo_pago = SelectField('Método de Pago', choices=[
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta')
    ], validators=[DataRequired()])
    comprobante = FileField('Comprobante', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Solo imágenes o PDF')
    ])
    notas = TextAreaField('Notas', validators=[Optional()])
