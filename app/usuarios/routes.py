"""
Rutas de Usuarios
Gestión de usuarios con jerarquía de 4 niveles
"""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.usuarios import bp
from app.auth.decoradores import login_required_with_role, misma_organizacion_required, misma_sucursal_required
from app.auth.auditoria import registrar_auditoria
from app.models import Usuario, Organizacion, Sucursal, db
from app.usuarios.forms import UsuarioForm


@bp.route('/')
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def index():
    """
    Listado de usuarios
    - Admin del despacho: ve todos
    - Director de organización: solo de su organización
    - Gerente de sucursal: solo de su sucursal
    """
    if current_user.es_admin_despacho():
        usuarios = Usuario.query.order_by(Usuario.nombre_completo).all()
    elif current_user.es_principal_organizacion():
        usuarios = Usuario.query.filter_by(
            organizacion_id=current_user.organizacion_id
        ).order_by(Usuario.nombre_completo).all()
    else:  # Gerente de sucursal
        usuarios = Usuario.query.filter_by(
            sucursal_id=current_user.sucursal_id
        ).order_by(Usuario.nombre_completo).all()

    return render_template('usuarios/index.html', usuarios=usuarios)


@bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def nuevo():
    """
    Crear un nuevo usuario

    Permisos de creación:
    - Admin del despacho: puede crear directores de organización
    - Director de organización: puede crear gerentes de sucursal y POS para su organización
    - Gerente de sucursal: puede crear POS para su sucursal
    """
    form = UsuarioForm()

    # Configurar opciones según el rol del usuario actual
    if current_user.es_admin_despacho():
        # Admin puede crear directores de organización
        organizaciones = Organizacion.query.filter_by(activa=True).order_by(Organizacion.nombre).all()
        form.organizacion_id.choices = [(0, 'Sin organización')] + [(org.id, org.nombre) for org in organizaciones]
        form.sucursal_id.choices = [(0, 'Sin sucursal')]
        form.rol.choices = [
            ('admin_despacho', 'Administrador del Despacho'),
            ('principal_organizacion', 'Director de Organización')
        ]

    elif current_user.es_principal_organizacion():
        # Director puede crear gerentes de sucursal y POS para su organización
        sucursales = Sucursal.query.filter_by(
            organizacion_id=current_user.organizacion_id,
            activa=True
        ).order_by(Sucursal.nombre).all()

        org = Organizacion.query.get(current_user.organizacion_id)
        form.organizacion_id.choices = [(org.id, org.nombre)]
        form.organizacion_id.data = org.id
        form.sucursal_id.choices = [(0, 'Seleccione sucursal')] + [(suc.id, suc.nombre) for suc in sucursales]
        form.rol.choices = [
            ('principal_sucursal', 'Gerente de Sucursal'),
            ('secundario_pos', 'Secundario (POS)')
        ]

    else:  # Gerente de sucursal
        # Gerente solo puede crear POS para su sucursal
        suc = Sucursal.query.get(current_user.sucursal_id)
        org = Organizacion.query.get(current_user.organizacion_id)
        form.organizacion_id.choices = [(org.id, org.nombre)]
        form.organizacion_id.data = org.id
        form.sucursal_id.choices = [(suc.id, suc.nombre)]
        form.sucursal_id.data = suc.id
        form.rol.choices = [('secundario_pos', 'Secundario (POS)')]

    if form.validate_on_submit():
        organizacion_id = form.organizacion_id.data if form.organizacion_id.data != 0 else None
        sucursal_id = form.sucursal_id.data if form.sucursal_id.data != 0 else None
        rol = form.rol.data

        # Validaciones según el rol a crear
        if rol == 'admin_despacho':
            # Admin no pertenece a ninguna organización/sucursal
            organizacion_id = None
            sucursal_id = None
            if not current_user.es_admin_despacho():
                flash('Solo el admin del despacho puede crear otros admins.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')

        elif rol == 'principal_organizacion':
            # Director necesita organización pero no sucursal
            if not organizacion_id:
                flash('Los directores de organización deben tener una organización asignada.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')
            sucursal_id = None
            if not current_user.es_admin_despacho():
                flash('Solo el admin del despacho puede crear directores de organización.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')

        elif rol == 'principal_sucursal':
            # Gerente necesita organización y sucursal
            if not organizacion_id or not sucursal_id:
                flash('Los gerentes de sucursal deben tener organización y sucursal asignadas.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')

            # Verificar que director solo crea para su organización
            if current_user.es_principal_organizacion():
                if organizacion_id != current_user.organizacion_id:
                    flash('No puedes crear usuarios para otra organización.', 'danger')
                    return redirect(url_for('usuarios.index'))

                # Verificar que la sucursal pertenezca a su organización
                sucursal = Sucursal.query.get(sucursal_id)
                if not sucursal or sucursal.organizacion_id != current_user.organizacion_id:
                    flash('La sucursal no pertenece a tu organización.', 'danger')
                    return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')

        elif rol == 'secundario_pos':
            # POS necesita organización y sucursal
            if not organizacion_id or not sucursal_id:
                flash('Los usuarios POS deben tener organización y sucursal asignadas.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')

            # Verificar permisos según rol del creador
            if current_user.es_principal_organizacion():
                if organizacion_id != current_user.organizacion_id:
                    flash('No puedes crear usuarios para otra organización.', 'danger')
                    return redirect(url_for('usuarios.index'))

                sucursal = Sucursal.query.get(sucursal_id)
                if not sucursal or sucursal.organizacion_id != current_user.organizacion_id:
                    flash('La sucursal no pertenece a tu organización.', 'danger')
                    return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')

            elif current_user.es_principal_sucursal():
                if sucursal_id != current_user.sucursal_id:
                    flash('Solo puedes crear usuarios para tu sucursal.', 'danger')
                    return redirect(url_for('usuarios.index'))

        # Crear nuevo usuario
        usuario = Usuario(
            username=form.username.data,
            email=form.email.data,
            nombre_completo=form.nombre_completo.data,
            rol=rol,
            organizacion_id=organizacion_id,
            sucursal_id=sucursal_id,
            activo=form.activo.data
        )

        # Establecer contraseña
        if form.password.data:
            usuario.set_password(form.password.data)
        else:
            flash('La contraseña es requerida para usuarios nuevos.', 'danger')
            return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')

        # Establecer permisos para usuarios secundarios
        if rol == 'secundario_pos':
            usuario.puede_registrar_ingresos = form.puede_registrar_ingresos.data
            usuario.puede_registrar_egresos = form.puede_registrar_egresos.data
            usuario.puede_editar_movimientos = form.puede_editar_movimientos.data
            usuario.puede_eliminar_movimientos = form.puede_eliminar_movimientos.data
            usuario.puede_ver_reportes = form.puede_ver_reportes.data

        db.session.add(usuario)
        db.session.commit()

        registrar_auditoria('create', 'usuario', usuario.id, {
            'username': usuario.username,
            'rol': usuario.rol
        })

        flash(f'Usuario "{usuario.username}" creado exitosamente.', 'success')
        return redirect(url_for('usuarios.index'))

    return render_template('usuarios/formulario.html', form=form, titulo='Nuevo Usuario')


@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def editar(id):
    """
    Editar un usuario existente
    """
    usuario = Usuario.query.get_or_404(id)

    # Verificar permisos
    if current_user.es_principal_organizacion():
        if usuario.organizacion_id != current_user.organizacion_id:
            flash('No puedes editar usuarios de otra organización.', 'danger')
            return redirect(url_for('usuarios.index'))
    elif current_user.es_principal_sucursal():
        if usuario.sucursal_id != current_user.sucursal_id:
            flash('No puedes editar usuarios de otra sucursal.', 'danger')
            return redirect(url_for('usuarios.index'))

    form = UsuarioForm(usuario_original=usuario, obj=usuario)

    # Configurar opciones según el rol del usuario actual
    if current_user.es_admin_despacho():
        organizaciones = Organizacion.query.filter_by(activa=True).order_by(Organizacion.nombre).all()
        form.organizacion_id.choices = [(0, 'Sin organización')] + [(org.id, org.nombre) for org in organizaciones]

        # Cargar sucursales de la organización del usuario
        if usuario.organizacion_id:
            sucursales = Sucursal.query.filter_by(
                organizacion_id=usuario.organizacion_id,
                activa=True
            ).order_by(Sucursal.nombre).all()
            form.sucursal_id.choices = [(0, 'Sin sucursal')] + [(suc.id, suc.nombre) for suc in sucursales]
        else:
            form.sucursal_id.choices = [(0, 'Sin sucursal')]

        form.rol.choices = [
            ('admin_despacho', 'Administrador del Despacho'),
            ('principal_organizacion', 'Director de Organización'),
            ('principal_sucursal', 'Gerente de Sucursal'),
            ('secundario_pos', 'Secundario (POS)')
        ]

    elif current_user.es_principal_organizacion():
        org = Organizacion.query.get(current_user.organizacion_id)
        form.organizacion_id.choices = [(org.id, org.nombre)]

        sucursales = Sucursal.query.filter_by(
            organizacion_id=current_user.organizacion_id,
            activa=True
        ).order_by(Sucursal.nombre).all()
        form.sucursal_id.choices = [(0, 'Sin sucursal')] + [(suc.id, suc.nombre) for suc in sucursales]

        form.rol.choices = [
            ('principal_sucursal', 'Gerente de Sucursal'),
            ('secundario_pos', 'Secundario (POS)')
        ]

    else:  # Gerente de sucursal
        suc = Sucursal.query.get(current_user.sucursal_id)
        org = Organizacion.query.get(current_user.organizacion_id)
        form.organizacion_id.choices = [(org.id, org.nombre)]
        form.sucursal_id.choices = [(suc.id, suc.nombre)]
        form.rol.choices = [('secundario_pos', 'Secundario (POS)')]

    if request.method == 'GET':
        # Pre-llenar el formulario con los datos del usuario
        form.username.data = usuario.username
        form.email.data = usuario.email
        form.nombre_completo.data = usuario.nombre_completo
        form.rol.data = usuario.rol
        form.organizacion_id.data = usuario.organizacion_id if usuario.organizacion_id else 0
        form.sucursal_id.data = usuario.sucursal_id if usuario.sucursal_id else 0
        form.activo.data = usuario.activo

        if usuario.rol == 'secundario_pos':
            form.puede_registrar_ingresos.data = usuario.puede_registrar_ingresos
            form.puede_registrar_egresos.data = usuario.puede_registrar_egresos
            form.puede_editar_movimientos.data = usuario.puede_editar_movimientos
            form.puede_eliminar_movimientos.data = usuario.puede_eliminar_movimientos
            form.puede_ver_reportes.data = usuario.puede_ver_reportes

    if form.validate_on_submit():
        organizacion_id = form.organizacion_id.data if form.organizacion_id.data != 0 else None
        sucursal_id = form.sucursal_id.data if form.sucursal_id.data != 0 else None
        rol = form.rol.data

        # Validaciones según el rol
        if rol == 'admin_despacho':
            organizacion_id = None
            sucursal_id = None
        elif rol == 'principal_organizacion':
            if not organizacion_id:
                flash('Los directores de organización deben tener una organización asignada.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Editar Usuario', usuario=usuario)
            sucursal_id = None
        elif rol in ['principal_sucursal', 'secundario_pos']:
            if not organizacion_id or not sucursal_id:
                flash(f'Los usuarios de tipo "{dict(form.rol.choices)[rol]}" deben tener organización y sucursal asignadas.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Editar Usuario', usuario=usuario)

        # Verificar permisos de edición
        if current_user.es_principal_organizacion():
            if organizacion_id != current_user.organizacion_id:
                flash('No puedes mover usuarios a otra organización.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Editar Usuario', usuario=usuario)
        elif current_user.es_principal_sucursal():
            if sucursal_id != current_user.sucursal_id:
                flash('No puedes mover usuarios a otra sucursal.', 'danger')
                return render_template('usuarios/formulario.html', form=form, titulo='Editar Usuario', usuario=usuario)

        # Actualizar datos del usuario
        usuario.username = form.username.data
        usuario.email = form.email.data
        usuario.nombre_completo = form.nombre_completo.data
        usuario.rol = rol
        usuario.organizacion_id = organizacion_id
        usuario.sucursal_id = sucursal_id
        usuario.activo = form.activo.data

        # Actualizar contraseña solo si se proporciona una nueva
        if form.password.data:
            usuario.set_password(form.password.data)

        # Actualizar permisos para usuarios secundarios
        if rol == 'secundario_pos':
            usuario.puede_registrar_ingresos = form.puede_registrar_ingresos.data
            usuario.puede_registrar_egresos = form.puede_registrar_egresos.data
            usuario.puede_editar_movimientos = form.puede_editar_movimientos.data
            usuario.puede_eliminar_movimientos = form.puede_eliminar_movimientos.data
            usuario.puede_ver_reportes = form.puede_ver_reportes.data

        db.session.commit()

        registrar_auditoria('update', 'usuario', usuario.id, {
            'username': usuario.username,
            'rol': usuario.rol
        })

        flash(f'Usuario "{usuario.username}" actualizado exitosamente.', 'success')
        return redirect(url_for('usuarios.index'))

    return render_template('usuarios/formulario.html', form=form, titulo='Editar Usuario', usuario=usuario)


@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def eliminar(id):
    """
    Eliminar (desactivar) un usuario
    """
    usuario = Usuario.query.get_or_404(id)

    # Verificar permisos
    if current_user.es_principal_organizacion():
        if usuario.organizacion_id != current_user.organizacion_id:
            flash('No puedes eliminar usuarios de otra organización.', 'danger')
            return redirect(url_for('usuarios.index'))
    elif current_user.es_principal_sucursal():
        if usuario.sucursal_id != current_user.sucursal_id:
            flash('No puedes eliminar usuarios de otra sucursal.', 'danger')
            return redirect(url_for('usuarios.index'))

    # No permitir que el usuario se elimine a sí mismo
    if usuario.id == current_user.id:
        flash('No puedes eliminar tu propio usuario.', 'danger')
        return redirect(url_for('usuarios.index'))

    # Desactivar en lugar de eliminar (soft delete)
    nombre = usuario.username
    usuario.activo = False
    db.session.commit()

    registrar_auditoria('delete', 'usuario', id, {
        'username': nombre
    })

    flash(f'Usuario "{nombre}" desactivado exitosamente.', 'success')
    return redirect(url_for('usuarios.index'))


@bp.route('/toggle_activo/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def toggle_activo(id):
    """
    Activar/desactivar usuario
    """
    usuario = Usuario.query.get_or_404(id)

    # Verificar permisos
    if current_user.es_principal_organizacion():
        if usuario.organizacion_id != current_user.organizacion_id:
            flash('No puedes modificar usuarios de otra organización.', 'danger')
            return redirect(url_for('usuarios.index'))
    elif current_user.es_principal_sucursal():
        if usuario.sucursal_id != current_user.sucursal_id:
            flash('No puedes modificar usuarios de otra sucursal.', 'danger')
            return redirect(url_for('usuarios.index'))

    # No permitir que el usuario se desactive a sí mismo
    if usuario.id == current_user.id:
        flash('No puedes desactivar tu propio usuario.', 'danger')
        return redirect(url_for('usuarios.index'))

    usuario.activo = not usuario.activo
    db.session.commit()

    registrar_auditoria('update', 'usuario', id, {
        'accion': 'activar' if usuario.activo else 'desactivar',
        'username': usuario.username
    })

    estado = 'activado' if usuario.activo else 'desactivado'
    flash(f'Usuario "{usuario.username}" {estado} exitosamente.', 'success')

    return redirect(url_for('usuarios.index'))
