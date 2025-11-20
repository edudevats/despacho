"""
Formularios para Proveedores
"""
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, Length, Regexp


class ProveedorForm(FlaskForm):
    """Formulario para crear/editar proveedores"""
    rfc = StringField('RFC', validators=[
        DataRequired(message='El RFC es obligatorio'),
        Length(min=12, max=13, message='El RFC debe tener 12 o 13 caracteres'),
        Regexp(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$', message='Formato de RFC inválido')
    ])
    razon_social = StringField('Razón Social', validators=[
        DataRequired(message='La razón social es obligatoria'),
        Length(max=200, message='Máximo 200 caracteres')
    ])
    nombre_comercial = StringField('Nombre Comercial', validators=[
        Optional(),
        Length(max=200, message='Máximo 200 caracteres')
    ])

    regimen_fiscal = SelectField('Régimen Fiscal', choices=[
        ('', 'Seleccionar...'),
        ('601', '601 - General de Ley Personas Morales'),
        ('603', '603 - Personas Morales con Fines no Lucrativos'),
        ('605', '605 - Sueldos y Salarios e Ingresos Asimilados a Salarios'),
        ('606', '606 - Arrendamiento'),
        ('607', '607 - Régimen de Enajenación o Adquisición de Bienes'),
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
    ], validators=[Optional()])

    # Contacto
    telefono = StringField('Teléfono', validators=[
        Optional(),
        Length(max=20, message='Máximo 20 caracteres')
    ])
    email = StringField('Email', validators=[
        Optional(),
        Email(message='Email inválido'),
        Length(max=100, message='Máximo 100 caracteres')
    ])

    # Dirección
    calle = StringField('Calle', validators=[
        Optional(),
        Length(max=200, message='Máximo 200 caracteres')
    ])
    numero_exterior = StringField('Número Exterior', validators=[
        Optional(),
        Length(max=20, message='Máximo 20 caracteres')
    ])
    numero_interior = StringField('Número Interior', validators=[
        Optional(),
        Length(max=20, message='Máximo 20 caracteres')
    ])
    colonia = StringField('Colonia', validators=[
        Optional(),
        Length(max=100, message='Máximo 100 caracteres')
    ])
    codigo_postal = StringField('Código Postal', validators=[
        Optional(),
        Length(min=5, max=5, message='El CP debe tener 5 dígitos'),
        Regexp(r'^\d{5}$', message='El CP debe ser numérico')
    ])
    ciudad = StringField('Ciudad', validators=[
        Optional(),
        Length(max=100, message='Máximo 100 caracteres')
    ])
    estado = StringField('Estado', validators=[
        Optional(),
        Length(max=100, message='Máximo 100 caracteres')
    ])
    pais = StringField('País', validators=[
        Optional(),
        Length(max=100, message='Máximo 100 caracteres')
    ], default='México')

    # Datos bancarios
    banco = StringField('Banco', validators=[
        Optional(),
        Length(max=100, message='Máximo 100 caracteres')
    ])
    cuenta_bancaria = StringField('Cuenta Bancaria', validators=[
        Optional(),
        Length(max=20, message='Máximo 20 caracteres')
    ])
    clabe = StringField('CLABE', validators=[
        Optional(),
        Length(min=18, max=18, message='La CLABE debe tener 18 dígitos'),
        Regexp(r'^\d{18}$', message='La CLABE debe ser numérica')
    ])

    # Categorización
    categoria_gasto = SelectField('Categoría Principal de Gasto', choices=[
        ('', 'Seleccionar...'),
        ('materiales', 'Materiales y Suministros'),
        ('servicios', 'Servicios Profesionales'),
        ('arrendamiento', 'Arrendamiento'),
        ('mantenimiento', 'Mantenimiento'),
        ('publicidad', 'Publicidad y Marketing'),
        ('transporte', 'Transporte y Logística'),
        ('tecnologia', 'Tecnología'),
        ('nomina', 'Nómina y Recursos Humanos'),
        ('seguros', 'Seguros'),
        ('otros', 'Otros')
    ], validators=[Optional()])

    # Alertas y control
    en_lista_negra = BooleanField('En Lista Negra (EFOS/EDOS)')
    activo = BooleanField('Proveedor Activo', default=True)

    # Notas
    notas = TextAreaField('Notas', validators=[
        Optional(),
        Length(max=500, message='Máximo 500 caracteres')
    ])

    submit = SubmitField('Guardar Proveedor')


class BuscarProveedorForm(FlaskForm):
    """Formulario de búsqueda de proveedores"""
    rfc = StringField('RFC', validators=[Optional()])
    razon_social = StringField('Razón Social', validators=[Optional()])
    categoria = SelectField('Categoría', choices=[
        ('', 'Todas'),
        ('materiales', 'Materiales y Suministros'),
        ('servicios', 'Servicios Profesionales'),
        ('arrendamiento', 'Arrendamiento'),
        ('mantenimiento', 'Mantenimiento'),
        ('publicidad', 'Publicidad y Marketing'),
        ('transporte', 'Transporte y Logística'),
        ('tecnologia', 'Tecnología'),
        ('nomina', 'Nómina y Recursos Humanos'),
        ('seguros', 'Seguros'),
        ('otros', 'Otros')
    ], validators=[Optional()])
    estado_activo = SelectField('Estado', choices=[
        ('', 'Todos'),
        ('activo', 'Activos'),
        ('inactivo', 'Inactivos')
    ], validators=[Optional()])
    lista_negra = SelectField('Lista Negra', choices=[
        ('', 'Todos'),
        ('si', 'En lista negra'),
        ('no', 'No en lista negra')
    ], validators=[Optional()])
