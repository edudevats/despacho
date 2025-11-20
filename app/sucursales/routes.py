"""
Rutas de Sucursales
Gestión de sucursales por organización
"""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.sucursales import bp
from app.sucursales.forms import SucursalForm
from app.auth.decoradores import login_required_with_role, misma_organizacion_required, misma_sucursal_required
from app.auth.auditoria import registrar_auditoria
from app.models import Sucursal, Organizacion, Usuario, db


@bp.route('/')
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion')
def index():
    """
    Listado de sucursales
    - Admin del despacho: ve todas
    - Director de organización: solo las de su organización
    """
    if current_user.es_admin_despacho():
        sucursales = Sucursal.query.order_by(Sucursal.nombre).all()
    else:
        sucursales = Sucursal.query.filter_by(
            organizacion_id=current_user.organizacion_id
        ).order_by(Sucursal.nombre).all()

    # Obtener estadísticas de cada sucursal
    stats = {}
    for suc in sucursales:
        stats[suc.id] = {
            'usuarios': Usuario.query.filter_by(sucursal_id=suc.id).count()
        }

    return render_template('sucursales/index.html', sucursales=sucursales, stats=stats)


@bp.route('/nueva', methods=['GET', 'POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion')
def nueva():
    """
    Crear nueva sucursal
    """
    form = SucursalForm()

    # Cargar organizaciones para el selector
    if current_user.es_admin_despacho():
        organizaciones = Organizacion.query.filter_by(activa=True).order_by(Organizacion.nombre).all()
        form.organizacion_id.choices = [(org.id, org.nombre) for org in organizaciones]
    else:
        # Director de organización solo puede crear en su organización
        org = Organizacion.query.get(current_user.organizacion_id)
        form.organizacion_id.choices = [(org.id, org.nombre)]
        form.organizacion_id.data = org.id

    if form.validate_on_submit():
        # Verificar permiso de organización
        if not current_user.es_admin_despacho() and form.organizacion_id.data != current_user.organizacion_id:
            flash('No puedes crear sucursales en otra organización.', 'danger')
            return render_template('sucursales/formulario.html', form=form, accion='nueva')

        # Verificar RFC único si se proporciona
        if form.rfc.data:
            existe = Sucursal.query.filter_by(rfc=form.rfc.data.upper()).first()
            if existe:
                flash(f'Ya existe una sucursal con el RFC "{form.rfc.data}".', 'warning')
                return render_template('sucursales/formulario.html', form=form, accion='nueva')

        # Crear la sucursal
        sucursal = Sucursal(
            organizacion_id=form.organizacion_id.data,
            nombre=form.nombre.data,
            razon_social=form.razon_social.data,
            rfc=form.rfc.data.upper() if form.rfc.data else None,
            direccion=form.direccion.data,
            telefono=form.telefono.data,
            email=form.email.data,
            activa=form.activa.data
        )

        db.session.add(sucursal)
        db.session.commit()

        registrar_auditoria('create', 'sucursal', sucursal.id, {
            'nombre': sucursal.nombre,
            'organizacion_id': sucursal.organizacion_id
        })

        flash(f'Sucursal "{sucursal.nombre}" creada exitosamente.', 'success')
        return redirect(url_for('sucursales.index'))

    return render_template('sucursales/formulario.html', form=form, accion='nueva')


@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion')
@misma_sucursal_required
def editar(id):
    """
    Editar sucursal
    """
    sucursal = Sucursal.query.get_or_404(id)
    form = SucursalForm(obj=sucursal)

    # Cargar organizaciones para el selector
    if current_user.es_admin_despacho():
        organizaciones = Organizacion.query.filter_by(activa=True).order_by(Organizacion.nombre).all()
        form.organizacion_id.choices = [(org.id, org.nombre) for org in organizaciones]
    else:
        # Director de organización solo puede ver su organización
        org = Organizacion.query.get(current_user.organizacion_id)
        form.organizacion_id.choices = [(org.id, org.nombre)]

    if form.validate_on_submit():
        # Verificar permiso de organización
        if not current_user.es_admin_despacho() and form.organizacion_id.data != current_user.organizacion_id:
            flash('No puedes mover sucursales a otra organización.', 'danger')
            return render_template('sucursales/formulario.html',
                                 form=form, accion='editar', sucursal=sucursal)

        # Verificar RFC único si se proporciona
        if form.rfc.data:
            existe = Sucursal.query.filter(
                Sucursal.rfc == form.rfc.data.upper(),
                Sucursal.id != id
            ).first()
            if existe:
                flash(f'Ya existe otra sucursal con el RFC "{form.rfc.data}".', 'warning')
                return render_template('sucursales/formulario.html',
                                     form=form, accion='editar', sucursal=sucursal)

        # Actualizar la sucursal
        nombre_anterior = sucursal.nombre
        sucursal.organizacion_id = form.organizacion_id.data
        sucursal.nombre = form.nombre.data
        sucursal.razon_social = form.razon_social.data
        sucursal.rfc = form.rfc.data.upper() if form.rfc.data else None
        sucursal.direccion = form.direccion.data
        sucursal.telefono = form.telefono.data
        sucursal.email = form.email.data
        sucursal.activa = form.activa.data

        db.session.commit()

        registrar_auditoria('update', 'sucursal', sucursal.id, {
            'nombre_anterior': nombre_anterior,
            'nombre_nuevo': sucursal.nombre
        })

        flash(f'Sucursal "{sucursal.nombre}" actualizada exitosamente.', 'success')
        return redirect(url_for('sucursales.index'))

    return render_template('sucursales/formulario.html',
                         form=form, accion='editar', sucursal=sucursal)


@bp.route('/detalle/<int:id>')
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
@misma_sucursal_required
def detalle(id):
    """
    Ver detalles de una sucursal
    """
    sucursal = Sucursal.query.get_or_404(id)

    # Obtener usuarios
    usuarios = Usuario.query.filter_by(sucursal_id=id).order_by(Usuario.nombre_completo).all()

    # Obtener estadísticas
    from app.models import CategoriaIngreso, CategoriaEgreso, Ingreso, Egreso
    from sqlalchemy import func, or_
    from decimal import Decimal

    stats = {
        'usuarios': len(usuarios),
        'categorias_ingreso_org': CategoriaIngreso.query.filter_by(organizacion_id=sucursal.organizacion_id).count(),
        'categorias_ingreso_suc': CategoriaIngreso.query.filter_by(sucursal_id=id).count(),
        'categorias_egreso_org': CategoriaEgreso.query.filter_by(organizacion_id=sucursal.organizacion_id).count(),
        'categorias_egreso_suc': CategoriaEgreso.query.filter_by(sucursal_id=id).count()
    }

    # Calcular totales de movimientos
    total_ingresos = db.session.query(func.sum(Ingreso.monto)).filter_by(sucursal_id=id).scalar() or Decimal('0.00')
    total_egresos = db.session.query(func.sum(Egreso.monto)).filter_by(sucursal_id=id).scalar() or Decimal('0.00')

    stats['total_ingresos'] = total_ingresos
    stats['total_egresos'] = total_egresos
    stats['balance'] = total_ingresos - total_egresos

    return render_template('sucursales/detalle.html',
                         sucursal=sucursal,
                         usuarios=usuarios,
                         stats=stats)


@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion')
@misma_sucursal_required
def eliminar(id):
    """
    Eliminar sucursal
    """
    sucursal = Sucursal.query.get_or_404(id)

    # Verificar si hay usuarios asociados
    usuarios_count = Usuario.query.filter_by(sucursal_id=id).count()

    if usuarios_count > 0:
        flash(f'No se puede eliminar la sucursal "{sucursal.nombre}" porque tiene {usuarios_count} usuario(s) asociado(s).', 'warning')
        return redirect(url_for('sucursales.index'))

    # Verificar si hay movimientos asociados
    from app.models import Ingreso, Egreso
    ingresos_count = Ingreso.query.filter_by(sucursal_id=id).count()
    egresos_count = Egreso.query.filter_by(sucursal_id=id).count()

    if ingresos_count > 0 or egresos_count > 0:
        flash(f'No se puede eliminar la sucursal "{sucursal.nombre}" porque tiene movimientos registrados. Puedes desactivarla en su lugar.', 'warning')
        return redirect(url_for('sucursales.index'))

    # Eliminar la sucursal
    nombre = sucursal.nombre
    db.session.delete(sucursal)
    db.session.commit()

    registrar_auditoria('delete', 'sucursal', id, {
        'nombre': nombre
    })

    flash(f'Sucursal "{nombre}" eliminada exitosamente.', 'success')
    return redirect(url_for('sucursales.index'))


@bp.route('/toggle_activa/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion')
@misma_sucursal_required
def toggle_activa(id):
    """
    Activar/desactivar sucursal
    """
    sucursal = Sucursal.query.get_or_404(id)

    sucursal.activa = not sucursal.activa
    db.session.commit()

    registrar_auditoria('update', 'sucursal', id, {
        'accion': 'activar' if sucursal.activa else 'desactivar',
        'nombre': sucursal.nombre
    })

    estado = 'activada' if sucursal.activa else 'desactivada'
    flash(f'Sucursal "{sucursal.nombre}" {estado} exitosamente.', 'success')

    return redirect(url_for('sucursales.index'))
