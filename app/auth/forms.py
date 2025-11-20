"""
Formularios de autenticación
"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    """Formulario de inicio de sesión"""
    username = StringField('Usuario',
                          validators=[DataRequired(), Length(min=3, max=80)],
                          render_kw={"placeholder": "Ingresa tu usuario"})

    password = PasswordField('Contraseña',
                            validators=[DataRequired()],
                            render_kw={"placeholder": "Ingresa tu contraseña"})

    remember_me = BooleanField('Recordarme')

    submit = SubmitField('Iniciar Sesión')
