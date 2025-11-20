"""
Rutas de Organizaciones
Gestión de organizaciones (solo para admin del despacho)
"""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required
from app.organizaciones import bp
from app.organizaciones.forms import OrganizacionForm
from app.auth.decoradores import admin_despacho_required
from app.auth.auditoria import registrar_auditoria
from app.models import Organizacion, Sucursal, Usuario, db


@bp.route('/')
@login_required
@admin_despacho_required
def index():
    """
    Listado de organizaciones
    """
    organizaciones = Organizacion.query.order_by(Organizacion.nombre).all()

    # Obtener estadísticas de cada organización
    stats = {}
    for org in organizaciones:
        stats[org.id] = {
            'sucursales': Sucursal.query.filter_by(organizacion_id=org.id).count(),
            'usuarios': Usuario.query.filter_by(organizacion_id=org.id).count()
        }

    return render_template('organizaciones/index.html', organizaciones=organizaciones, stats=stats)


@bp.route('/nueva', methods=['GET', 'POST'])
@login_required
@admin_despacho_required
def nueva():
    """
    Crear nueva organización
    """
    form = OrganizacionForm()

    if form.validate_on_submit():
        # Verificar que no exista una organización con el mismo RFC
        existe = Organizacion.query.filter_by(rfc=form.rfc.data.upper()).first()

        if existe:
            flash(f'Ya existe una organización con el RFC "{form.rfc.data}".', 'warning')
            return render_template('organizaciones/formulario.html', form=form, accion='nueva')

        # Crear la organización
        organizacion = Organizacion(
            nombre=form.nombre.data,
            razon_social=form.razon_social.data,
            rfc=form.rfc.data.upper(),
            direccion=form.direccion.data,
            telefono=form.telefono.data,
            email=form.email.data,
            activa=form.activa.data
        )

        db.session.add(organizacion)
        db.session.commit()

        registrar_auditoria('create', 'organizacion', organizacion.id, {
            'nombre': organizacion.nombre,
            'rfc': organizacion.rfc
        })

        flash(f'Organización "{organizacion.nombre}" creada exitosamente.', 'success')
        return redirect(url_for('organizaciones.index'))

    return render_template('organizaciones/formulario.html', form=form, accion='nueva')


@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_despacho_required
def editar(id):
    """
    Editar organización
    """
    organizacion = Organizacion.query.get_or_404(id)
    form = OrganizacionForm(obj=organizacion)

    if form.validate_on_submit():
        # Verificar que no exista otra organización con el mismo RFC
        existe = Organizacion.query.filter(
            Organizacion.rfc == form.rfc.data.upper(),
            Organizacion.id != id
        ).first()

        if existe:
            flash(f'Ya existe otra organización con el RFC "{form.rfc.data}".', 'warning')
            return render_template('organizaciones/formulario.html',
                                 form=form, accion='editar', organizacion=organizacion)

        # Actualizar la organización
        nombre_anterior = organizacion.nombre
        organizacion.nombre = form.nombre.data
        organizacion.razon_social = form.razon_social.data
        organizacion.rfc = form.rfc.data.upper()
        organizacion.direccion = form.direccion.data
        organizacion.telefono = form.telefono.data
        organizacion.email = form.email.data
        organizacion.activa = form.activa.data

        db.session.commit()

        registrar_auditoria('update', 'organizacion', organizacion.id, {
            'nombre_anterior': nombre_anterior,
            'nombre_nuevo': organizacion.nombre
        })

        flash(f'Organización "{organizacion.nombre}" actualizada exitosamente.', 'success')
        return redirect(url_for('organizaciones.index'))

    return render_template('organizaciones/formulario.html',
                         form=form, accion='editar', organizacion=organizacion)


@bp.route('/detalle/<int:id>')
@login_required
@admin_despacho_required
def detalle(id):
    """
    Ver detalles de una organización
    """
    organizacion = Organizacion.query.get_or_404(id)

    # Obtener sucursales
    sucursales = Sucursal.query.filter_by(organizacion_id=id).order_by(Sucursal.nombre).all()

    # Obtener usuarios
    usuarios = Usuario.query.filter_by(organizacion_id=id).order_by(Usuario.nombre_completo).all()

    # Obtener estadísticas
    from app.models import CategoriaIngreso, CategoriaEgreso, Proveedor, Ingreso, Egreso
    from sqlalchemy import func
    from decimal import Decimal

    stats = {
        'sucursales': len(sucursales),
        'usuarios': len(usuarios),
        'categorias_ingreso': CategoriaIngreso.query.filter_by(organizacion_id=id).count(),
        'categorias_egreso': CategoriaEgreso.query.filter_by(organizacion_id=id).count(),
        'proveedores': Proveedor.query.filter_by(organizacion_id=id).count()
    }

    # Calcular totales de movimientos de todas las sucursales
    total_ingresos = Decimal('0.00')
    total_egresos = Decimal('0.00')

    for sucursal in sucursales:
        ingresos_sum = db.session.query(func.sum(Ingreso.monto)).filter_by(sucursal_id=sucursal.id).scalar() or Decimal('0.00')
        egresos_sum = db.session.query(func.sum(Egreso.monto)).filter_by(sucursal_id=sucursal.id).scalar() or Decimal('0.00')
        total_ingresos += ingresos_sum
        total_egresos += egresos_sum

    stats['total_ingresos'] = total_ingresos
    stats['total_egresos'] = total_egresos
    stats['balance'] = total_ingresos - total_egresos

    return render_template('organizaciones/detalle.html',
                         organizacion=organizacion,
                         sucursales=sucursales,
                         usuarios=usuarios,
                         stats=stats)


@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_despacho_required
def eliminar(id):
    """
    Eliminar organización
    """
    organizacion = Organizacion.query.get_or_404(id)

    # Verificar si hay sucursales asociadas
    sucursales_count = Sucursal.query.filter_by(organizacion_id=id).count()

    if sucursales_count > 0:
        flash(f'No se puede eliminar la organización "{organizacion.nombre}" porque tiene {sucursales_count} sucursal(es) asociada(s). Debes eliminar las sucursales primero o desactivar la organización.', 'warning')
        return redirect(url_for('organizaciones.index'))

    # Verificar si hay usuarios asociados
    usuarios_count = Usuario.query.filter_by(organizacion_id=id).count()

    if usuarios_count > 0:
        flash(f'No se puede eliminar la organización "{organizacion.nombre}" porque tiene {usuarios_count} usuario(s) asociado(s).', 'warning')
        return redirect(url_for('organizaciones.index'))

    # Eliminar la organización
    nombre = organizacion.nombre
    db.session.delete(organizacion)
    db.session.commit()

    registrar_auditoria('delete', 'organizacion', id, {
        'nombre': nombre
    })

    flash(f'Organización "{nombre}" eliminada exitosamente.', 'success')
    return redirect(url_for('organizaciones.index'))


@bp.route('/toggle_activa/<int:id>', methods=['POST'])
@login_required
@admin_despacho_required
def toggle_activa(id):
    """
    Activar/desactivar organización
    """
    organizacion = Organizacion.query.get_or_404(id)

    organizacion.activa = not organizacion.activa
    db.session.commit()

    registrar_auditoria('update', 'organizacion', id, {
        'accion': 'activar' if organizacion.activa else 'desactivar',
        'nombre': organizacion.nombre
    })

    estado = 'activada' if organizacion.activa else 'desactivada'
    flash(f'Organización "{organizacion.nombre}" {estado} exitosamente.', 'success')

    return redirect(url_for('organizaciones.index'))
