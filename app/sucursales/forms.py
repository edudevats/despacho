"""
Formularios para el módulo de Sucursales
"""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, SelectField
from wtforms.validators import DataRequired, Length, Email, Optional, Regexp


class SucursalForm(FlaskForm):
    """Formulario para crear/editar sucursales"""

    organizacion_id = SelectField('Organización', coerce=int, validators=[
        DataRequired('La organización es obligatoria')
    ])

    nombre = StringField('Nombre Comercial', validators=[
        DataRequired('El nombre es obligatorio'),
        Length(min=3, max=200, message='El nombre debe tener entre 3 y 200 caracteres')
    ])

    razon_social = StringField('Razón Social', validators=[
        Optional(),
        Length(max=200, message='La razón social no debe exceder 200 caracteres')
    ])

    rfc = StringField('RFC', validators=[
        Optional(),
        Length(min=12, max=13, message='El RFC debe tener 12 o 13 caracteres'),
        Regexp(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$', message='Formato de RFC inválido')
    ])

    direccion = TextAreaField('Dirección', validators=[
        Optional(),
        Length(max=500, message='La dirección no debe exceder 500 caracteres')
    ])

    telefono = StringField('Teléfono', validators=[
        Optional(),
        Length(max=20, message='El teléfono no debe exceder 20 caracteres')
    ])

    email = StringField('Email', validators=[
        Optional(),
        Email(message='Email inválido'),
        Length(max=120, message='El email no debe exceder 120 caracteres')
    ])

    activa = BooleanField('Activa', default=True)
