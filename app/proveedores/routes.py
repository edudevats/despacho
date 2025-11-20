"""
Rutas de Proveedores
Gestión de proveedores y validación de RFC
"""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.proveedores import bp
from app.auth.decoradores import login_required_with_role
from app.models import db, Proveedor, FacturaCFDI, Egreso
from app.proveedores.forms import ProveedorForm, BuscarProveedorForm
from app.cfdi.parser import validar_rfc


@bp.route('/')
@login_required
def index():
    """
    Listado de proveedores con filtros
    """
    form = BuscarProveedorForm(request.args, meta={'csrf': False})

    # Query base
    query = Proveedor.query

    # Filtrar por clínica si no es admin
    if not current_user.es_admin_despacho():
        query = query.filter_by(sucursal_id=current_user.sucursal_id)

    # Aplicar filtros
    rfc_buscar = request.args.get('rfc', '').strip()
    razon_social = request.args.get('razon_social', '').strip()
    categoria = request.args.get('categoria', '')
    estado_activo = request.args.get('estado_activo', '')
    lista_negra = request.args.get('lista_negra', '')

    if rfc_buscar:
        query = query.filter(Proveedor.rfc.like(f'%{rfc_buscar}%'))

    if razon_social:
        query = query.filter(Proveedor.razon_social.like(f'%{razon_social}%'))

    if categoria:
        query = query.filter_by(categoria_gasto=categoria)

    if estado_activo == 'activo':
        query = query.filter_by(activo=True)
    elif estado_activo == 'inactivo':
        query = query.filter_by(activo=False)

    if lista_negra == 'si':
        query = query.filter_by(en_lista_negra=True)
    elif lista_negra == 'no':
        query = query.filter_by(en_lista_negra=False)

    # Ordenar por razón social
    proveedores = query.order_by(Proveedor.razon_social).all()

    return render_template('proveedores/index.html',
                         proveedores=proveedores,
                         form=form)


@bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def nuevo():
    """
    Crear nuevo proveedor
    """
    form = ProveedorForm()

    if form.validate_on_submit():
        # Validar RFC
        rfc = form.rfc.data.strip().upper()
        if not validar_rfc(rfc):
            flash('El RFC ingresado no es válido.', 'danger')
            return render_template('proveedores/form.html', form=form, titulo='Nuevo Proveedor')

        # Verificar si el RFC ya existe
        proveedor_existente = Proveedor.query.filter_by(rfc=rfc).first()
        if proveedor_existente:
            flash(f'Ya existe un proveedor con el RFC {rfc}.', 'warning')
            return redirect(url_for('proveedores.detalle', id=proveedor_existente.id))

        # Crear proveedor
        proveedor = Proveedor(
            rfc=rfc,
            razon_social=form.razon_social.data.strip(),
            nombre_comercial=form.nombre_comercial.data.strip() if form.nombre_comercial.data else None,
            regimen_fiscal=form.regimen_fiscal.data if form.regimen_fiscal.data else None,
            telefono=form.telefono.data.strip() if form.telefono.data else None,
            email=form.email.data.strip() if form.email.data else None,
            calle=form.calle.data.strip() if form.calle.data else None,
            numero_exterior=form.numero_exterior.data.strip() if form.numero_exterior.data else None,
            numero_interior=form.numero_interior.data.strip() if form.numero_interior.data else None,
            colonia=form.colonia.data.strip() if form.colonia.data else None,
            codigo_postal=form.codigo_postal.data.strip() if form.codigo_postal.data else None,
            ciudad=form.ciudad.data.strip() if form.ciudad.data else None,
            estado=form.estado.data.strip() if form.estado.data else None,
            pais=form.pais.data.strip() if form.pais.data else 'México',
            banco=form.banco.data.strip() if form.banco.data else None,
            cuenta_bancaria=form.cuenta_bancaria.data.strip() if form.cuenta_bancaria.data else None,
            clabe=form.clabe.data.strip() if form.clabe.data else None,
            categoria_gasto=form.categoria_gasto.data if form.categoria_gasto.data else None,
            en_lista_negra=form.en_lista_negra.data,
            activo=form.activo.data,
            notas=form.notas.data.strip() if form.notas.data else None,
            sucursal_id=current_user.sucursal_id if not current_user.es_admin_despacho() else None
        )

        db.session.add(proveedor)
        db.session.commit()

        flash(f'Proveedor {proveedor.razon_social} creado exitosamente.', 'success')
        return redirect(url_for('proveedores.detalle', id=proveedor.id))

    return render_template('proveedores/form.html', form=form, titulo='Nuevo Proveedor')


@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def editar(id):
    """
    Editar proveedor existente
    """
    proveedor = Proveedor.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if proveedor.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para editar este proveedor.', 'danger')
            return redirect(url_for('proveedores.index'))

    form = ProveedorForm(obj=proveedor)

    if form.validate_on_submit():
        # Validar RFC
        rfc = form.rfc.data.strip().upper()
        if not validar_rfc(rfc):
            flash('El RFC ingresado no es válido.', 'danger')
            return render_template('proveedores/form.html', form=form, titulo='Editar Proveedor', proveedor=proveedor)

        # Verificar si el RFC ya existe en otro proveedor
        if rfc != proveedor.rfc:
            proveedor_existente = Proveedor.query.filter_by(rfc=rfc).first()
            if proveedor_existente:
                flash(f'Ya existe otro proveedor con el RFC {rfc}.', 'warning')
                return render_template('proveedores/form.html', form=form, titulo='Editar Proveedor', proveedor=proveedor)

        # Actualizar datos
        proveedor.rfc = rfc
        proveedor.razon_social = form.razon_social.data.strip()
        proveedor.nombre_comercial = form.nombre_comercial.data.strip() if form.nombre_comercial.data else None
        proveedor.regimen_fiscal = form.regimen_fiscal.data if form.regimen_fiscal.data else None
        proveedor.telefono = form.telefono.data.strip() if form.telefono.data else None
        proveedor.email = form.email.data.strip() if form.email.data else None
        proveedor.calle = form.calle.data.strip() if form.calle.data else None
        proveedor.numero_exterior = form.numero_exterior.data.strip() if form.numero_exterior.data else None
        proveedor.numero_interior = form.numero_interior.data.strip() if form.numero_interior.data else None
        proveedor.colonia = form.colonia.data.strip() if form.colonia.data else None
        proveedor.codigo_postal = form.codigo_postal.data.strip() if form.codigo_postal.data else None
        proveedor.ciudad = form.ciudad.data.strip() if form.ciudad.data else None
        proveedor.estado = form.estado.data.strip() if form.estado.data else None
        proveedor.pais = form.pais.data.strip() if form.pais.data else 'México'
        proveedor.banco = form.banco.data.strip() if form.banco.data else None
        proveedor.cuenta_bancaria = form.cuenta_bancaria.data.strip() if form.cuenta_bancaria.data else None
        proveedor.clabe = form.clabe.data.strip() if form.clabe.data else None
        proveedor.categoria_gasto = form.categoria_gasto.data if form.categoria_gasto.data else None
        proveedor.en_lista_negra = form.en_lista_negra.data
        proveedor.activo = form.activo.data
        proveedor.notas = form.notas.data.strip() if form.notas.data else None

        db.session.commit()

        flash(f'Proveedor {proveedor.razon_social} actualizado exitosamente.', 'success')
        return redirect(url_for('proveedores.detalle', id=proveedor.id))

    return render_template('proveedores/form.html', form=form, titulo='Editar Proveedor', proveedor=proveedor)


@bp.route('/detalle/<int:id>')
@login_required
def detalle(id):
    """
    Ver detalles de un proveedor
    """
    proveedor = Proveedor.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if proveedor.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para ver este proveedor.', 'danger')
            return redirect(url_for('proveedores.index'))

    # Obtener CFDIs del proveedor
    cfdis = FacturaCFDI.query.filter_by(proveedor_id=proveedor.id).order_by(FacturaCFDI.fecha_emision.desc()).limit(10).all()

    # Calcular total de gastos
    total_facturado = db.session.query(db.func.sum(FacturaCFDI.total)).filter_by(proveedor_id=proveedor.id).scalar() or 0

    return render_template('proveedores/detalle.html',
                         proveedor=proveedor,
                         cfdis=cfdis,
                         total_facturado=total_facturado)


@bp.route('/toggle_activo/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def toggle_activo(id):
    """
    Activar/desactivar proveedor
    """
    proveedor = Proveedor.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if proveedor.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para modificar este proveedor.', 'danger')
            return redirect(url_for('proveedores.index'))

    proveedor.activo = not proveedor.activo
    db.session.commit()

    estado = 'activado' if proveedor.activo else 'desactivado'
    flash(f'Proveedor {proveedor.razon_social} {estado}.', 'success')

    return redirect(url_for('proveedores.detalle', id=id))


@bp.route('/toggle_lista_negra/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def toggle_lista_negra(id):
    """
    Marcar/desmarcar proveedor en lista negra EFOS/EDOS
    """
    proveedor = Proveedor.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if proveedor.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para modificar este proveedor.', 'danger')
            return redirect(url_for('proveedores.index'))

    proveedor.en_lista_negra = not proveedor.en_lista_negra
    db.session.commit()

    if proveedor.en_lista_negra:
        flash(f'Proveedor {proveedor.razon_social} marcado en lista negra EFOS/EDOS.', 'warning')
    else:
        flash(f'Proveedor {proveedor.razon_social} removido de lista negra.', 'success')

    return redirect(url_for('proveedores.detalle', id=id))


@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def eliminar(id):
    """
    Eliminar proveedor (solo si no tiene facturas asociadas)
    """
    proveedor = Proveedor.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if proveedor.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para eliminar este proveedor.', 'danger')
            return redirect(url_for('proveedores.index'))

    # Verificar si tiene facturas asociadas
    facturas_count = FacturaCFDI.query.filter_by(proveedor_id=proveedor.id).count()
    if facturas_count > 0:
        flash(f'No se puede eliminar el proveedor porque tiene {facturas_count} facturas asociadas. Desactívalo en su lugar.', 'danger')
        return redirect(url_for('proveedores.detalle', id=id))

    razon_social = proveedor.razon_social
    db.session.delete(proveedor)
    db.session.commit()

    flash(f'Proveedor {razon_social} eliminado exitosamente.', 'success')
    return redirect(url_for('proveedores.index'))
