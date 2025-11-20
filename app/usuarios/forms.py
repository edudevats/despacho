"""
Formularios para gestión de usuarios
"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Optional
from app.models import Usuario


class UsuarioForm(FlaskForm):
    """
    Formulario para crear y editar usuarios
    """
    username = StringField('Usuario', validators=[
        DataRequired(message='El nombre de usuario es requerido'),
        Length(min=3, max=80, message='El usuario debe tener entre 3 y 80 caracteres')
    ])

    email = StringField('Email', validators=[
        DataRequired(message='El email es requerido'),
        Email(message='Email inválido')
    ])

    nombre_completo = StringField('Nombre Completo', validators=[
        DataRequired(message='El nombre completo es requerido'),
        Length(max=200)
    ])

    password = PasswordField('Contraseña', validators=[
        Length(min=6, message='La contraseña debe tener al menos 6 caracteres')
    ])

    password_confirm = PasswordField('Confirmar Contraseña', validators=[
        EqualTo('password', message='Las contraseñas deben coincidir')
    ])

    rol = SelectField('Rol', choices=[
        ('admin_despacho', 'Administrador Despacho'),
        ('principal_organizacion', 'Director de Organización'),
        ('principal_sucursal', 'Gerente de Sucursal'),
        ('secundario_pos', 'Secundario (POS)')
    ], validators=[DataRequired(message='Debe seleccionar un rol')])

    organizacion_id = SelectField('Organización', coerce=int, validators=[Optional()])
    sucursal_id = SelectField('Sucursal', coerce=int, validators=[Optional()])

    # Permisos para usuarios secundarios
    puede_registrar_ingresos = BooleanField('Puede registrar ingresos', default=True)
    puede_registrar_egresos = BooleanField('Puede registrar egresos', default=True)
    puede_editar_movimientos = BooleanField('Puede editar movimientos', default=False)
    puede_eliminar_movimientos = BooleanField('Puede eliminar movimientos', default=False)
    puede_ver_reportes = BooleanField('Puede ver reportes', default=False)

    activo = BooleanField('Usuario Activo', default=True)

    submit = SubmitField('Guardar Usuario')

    def __init__(self, usuario_original=None, *args, **kwargs):
        super(UsuarioForm, self).__init__(*args, **kwargs)
        self.usuario_original = usuario_original

    def validate_username(self, username):
        """Valida que el username sea único"""
        if self.usuario_original is None or username.data != self.usuario_original.username:
            usuario = Usuario.query.filter_by(username=username.data).first()
            if usuario is not None:
                raise ValidationError('Este nombre de usuario ya está en uso.')

    def validate_email(self, email):
        """Valida que el email sea único"""
        if self.usuario_original is None or email.data != self.usuario_original.email:
            usuario = Usuario.query.filter_by(email=email.data).first()
            if usuario is not None:
                raise ValidationError('Este email ya está registrado.')
