"""
Formularios de CFDI
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import SelectField, StringField, DecimalField, DateField, TextAreaField, BooleanField
from wtforms.validators import DataRequired, Optional, Length


class UploadCFDIForm(FlaskForm):
    """Formulario para subir archivos XML CFDI"""

    # Selector de sucursal (solo para admin_despacho y directores)
    sucursal_id = SelectField('Sucursal',
                            coerce=int,
                            validators=[Optional()])

    xml_file = FileField('Archivo XML', validators=[
        FileRequired('Debes seleccionar un archivo XML'),
        FileAllowed(['xml'], 'Solo se permiten archivos XML')
    ])

    # Opcional: asociar con movimiento existente
    movimiento_id = SelectField('Asociar con Movimiento (opcional)',
                               coerce=int,
                               validators=[Optional()])

    notas = TextAreaField('Notas', validators=[Length(max=500)])


class AsociarCFDIForm(FlaskForm):
    """Formulario para asociar CFDI con movimiento"""
    movimiento_id = SelectField('Movimiento',
                                coerce=int,
                                validators=[DataRequired('Debes seleccionar un movimiento')])

    crear_movimiento_si_no_existe = BooleanField('Crear movimiento automáticamente si no existe', default=True)
