"""
Formularios de Categorías
"""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField
from wtforms.validators import DataRequired, Length


class CategoriaForm(FlaskForm):
    """Formulario para crear/editar categorías (tanto ingresos como egresos)"""
    nombre = StringField('Nombre', validators=[
        DataRequired('El nombre es obligatorio'),
        Length(min=2, max=100, message='El nombre debe tener entre 2 y 100 caracteres')
    ])

    descripcion = TextAreaField('Descripción', validators=[
        Length(max=500, message='La descripción no puede exceder 500 caracteres')
    ])

    activa = BooleanField('Activa', default=True)
