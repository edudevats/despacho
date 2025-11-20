"""
Rutas de autenticación
"""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app.auth import bp
from app.auth.forms import LoginForm
from app.auth.auditoria import registrar_login, registrar_logout
from app.models import Usuario, db
from datetime import datetime


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Pantalla de inicio de sesión
    """
    # Si ya está autenticado, redirigir al dashboard correspondiente
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()

    if form.validate_on_submit():
        # Buscar usuario
        usuario = Usuario.query.filter_by(username=form.username.data).first()

        # Verificar contraseña
        if usuario is None or not usuario.check_password(form.password.data):
            flash('Usuario o contraseña incorrectos.', 'danger')
            return redirect(url_for('auth.login'))

        # Verificar que el usuario esté activo
        if not usuario.activo:
            flash('Tu cuenta está desactivada. Contacta al administrador.', 'warning')
            return redirect(url_for('auth.login'))

        # Login exitoso
        login_user(usuario, remember=form.remember_me.data)

        # Actualizar último acceso
        usuario.ultimo_acceso = datetime.utcnow()
        db.session.commit()

        # Registrar en auditoría
        registrar_login(usuario)

        flash(f'¡Bienvenido, {usuario.nombre_completo or usuario.username}!', 'success')

        # Redirigir a la página solicitada o al dashboard
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('main.index')

        return redirect(next_page)

    return render_template('auth/login.html', form=form)


@bp.route('/logout')
def logout():
    """
    Cerrar sesión
    """
    if current_user.is_authenticated:
        registrar_logout(current_user)

    logout_user()
    flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('auth.login'))
