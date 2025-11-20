"""
Rutas de CFDI
Gestión de facturas digitales XML/CFDI
"""
import os
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from app.cfdi import bp
from app.auth.decoradores import login_required_with_role
from app.models import db, FacturaCFDI, Proveedor, Ingreso, Egreso, Sucursal, Organizacion
from app.cfdi.forms import UploadCFDIForm, AsociarCFDIForm
from app.cfdi.parser import parse_xml_cfdi, validar_rfc


@bp.route('/')
@login_required
def index():
    """
    Listado de facturas CFDI
    """
    # Filtros
    organizacion_id = request.args.get('organizacion_id', type=int)
    sucursal_id = request.args.get('sucursal_id', type=int)
    proveedor_id = request.args.get('proveedor_id', type=int)
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    tipo = request.args.get('tipo', '')  # ingreso o egreso
    validado = request.args.get('validado', '')  # 'si', 'no'

    # Query base
    query = FacturaCFDI.query

    # Aplicar filtros según el rol
    if current_user.es_admin_despacho():
        # Admin despacho puede ver todas las organizaciones
        organizaciones = Organizacion.query.filter_by(activa=True).order_by(Organizacion.nombre).all()

        # Filtrar sucursales según organización seleccionada
        if organizacion_id:
            sucursales = Sucursal.query.filter_by(organizacion_id=organizacion_id, activa=True).order_by(Sucursal.nombre).all()
            sucursales_ids = [s.id for s in sucursales]
            if sucursales_ids:
                query = query.filter(FacturaCFDI.sucursal_id.in_(sucursales_ids))
        else:
            sucursales = Sucursal.query.filter_by(activa=True).order_by(Sucursal.nombre).all()

        # Filtro adicional por sucursal específica
        if sucursal_id:
            query = query.filter_by(sucursal_id=sucursal_id)

    elif current_user.es_principal_organizacion():
        organizacion_id = current_user.organizacion_id
        organizaciones = [Organizacion.query.get(organizacion_id)]

        sucursales_ids = [s.id for s in Sucursal.query.filter_by(organizacion_id=organizacion_id).all()]
        sucursales = Sucursal.query.filter_by(organizacion_id=organizacion_id, activa=True).order_by(Sucursal.nombre).all()

        if sucursal_id:
            query = query.filter_by(sucursal_id=sucursal_id)
        else:
            if sucursales_ids:
                query = query.filter(FacturaCFDI.sucursal_id.in_(sucursales_ids))
    else:
        organizacion_id = current_user.organizacion_id
        organizaciones = [Organizacion.query.get(organizacion_id)]
        sucursales = [Sucursal.query.get(current_user.sucursal_id)]
        query = query.filter_by(sucursal_id=current_user.sucursal_id)

    # Filtros adicionales
    if proveedor_id:
        query = query.filter_by(proveedor_id=proveedor_id)

    if fecha_inicio:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            query = query.filter(FacturaCFDI.fecha_emision >= fecha_inicio_dt)
        except ValueError:
            pass

    if fecha_fin:
        try:
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
            query = query.filter(FacturaCFDI.fecha_emision <= fecha_fin_dt)
        except ValueError:
            pass

    if tipo:
        query = query.filter_by(tipo_comprobante=tipo)

    if validado == 'si':
        query = query.filter_by(validado_sat=True)
    elif validado == 'no':
        query = query.filter_by(validado_sat=False)

    # Ordenar por fecha de emisión descendente
    facturas = query.order_by(FacturaCFDI.fecha_emision.desc()).limit(200).all()

    # Obtener proveedores para el filtro (filtrados por organización)
    if current_user.es_admin_despacho():
        if organizacion_id:
            # Filtrar proveedores por organización seleccionada
            proveedores = Proveedor.query.filter_by(
                organizacion_id=organizacion_id,
                activo=True
            ).order_by(Proveedor.razon_social).all()
        else:
            # Todos los proveedores activos
            proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.razon_social).all()
    elif current_user.es_principal_organizacion():
        # Director ve proveedores de su organización
        proveedores = Proveedor.query.filter_by(
            organizacion_id=current_user.organizacion_id,
            activo=True
        ).order_by(Proveedor.razon_social).all()
    else:
        # Gerente/POS ve proveedores de su organización
        proveedores = Proveedor.query.filter_by(
            organizacion_id=current_user.organizacion_id,
            activo=True
        ).order_by(Proveedor.razon_social).all()

    return render_template('cfdi/index.html',
                         facturas=facturas,
                         organizaciones=organizaciones,
                         sucursales=sucursales,
                         proveedores=proveedores)


@bp.route('/upload', methods=['GET', 'POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def upload():
    """
    Subir y procesar archivo XML CFDI
    """
    form = UploadCFDIForm()

    # Configurar selector de sucursal según el rol
    if current_user.es_admin_despacho():
        sucursales = Sucursal.query.filter_by(activa=True).order_by(Sucursal.nombre).all()
        form.sucursal_id.choices = [(0, 'Seleccione una sucursal')] + [
            (s.id, s.nombre) for s in sucursales
        ]
        # Obtener sucursal seleccionada del formulario o query string
        sucursal_filtro_id = request.form.get('sucursal_id', type=int) or request.args.get('sucursal_id', type=int)
    else:
        # Para usuarios de sucursal, usar su sucursal automáticamente
        sucursal_filtro_id = current_user.sucursal_id
        form.sucursal_id.data = sucursal_filtro_id

    # Cargar egresos disponibles para asociación (sin CFDI asociado)
    # Filtrar por sucursal seleccionada si existe
    if current_user.es_admin_despacho():
        query = Egreso.query.outerjoin(FacturaCFDI).filter(FacturaCFDI.id == None)
        if sucursal_filtro_id and sucursal_filtro_id != 0:
            query = query.filter(Egreso.sucursal_id == sucursal_filtro_id)
        egresos = query.order_by(Egreso.fecha.desc()).limit(100).all()
    else:
        egresos = Egreso.query.outerjoin(FacturaCFDI).filter(
            FacturaCFDI.id == None,
            Egreso.sucursal_id == current_user.sucursal_id
        ).order_by(Egreso.fecha.desc()).limit(100).all()

    form.movimiento_id.choices = [(0, 'No asociar ahora')] + [
        (e.id, f'EGRESO - {e.fecha.strftime("%Y-%m-%d")} - ${e.monto:,.2f} - {e.categoria.nombre} - {e.notas[:40] if e.notas else "Sin notas"}')
        for e in egresos
    ]

    if form.validate_on_submit():
        xml_file = form.xml_file.data
        filename = secure_filename(xml_file.filename)

        # Crear directorio de uploads si no existe
        upload_folder = os.path.join(current_app.root_path, 'uploads', 'cfdi')
        os.makedirs(upload_folder, exist_ok=True)

        # Guardar archivo temporalmente
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f'{timestamp}_{filename}'
        filepath = os.path.join(upload_folder, unique_filename)
        xml_file.save(filepath)

        # Parsear XML
        datos = parse_xml_cfdi(filepath)

        if not datos:
            flash('Error al procesar el archivo XML. Verifica que sea un CFDI válido.', 'danger')
            os.remove(filepath)
            return render_template('cfdi/upload.html', form=form)

        # Validar RFC del emisor
        if not validar_rfc(datos.get('emisor_rfc', '')):
            flash('El RFC del emisor no es válido.', 'warning')

        # Verificar si ya existe este UUID
        uuid = datos.get('uuid')
        factura_existente = FacturaCFDI.query.filter_by(uuid=uuid).first()
        if factura_existente:
            flash(f'Este CFDI ya fue registrado anteriormente (UUID: {uuid}).', 'warning')
            os.remove(filepath)
            return redirect(url_for('cfdi.detalle', id=factura_existente.id))

        # Determinar la clínica a usar
        if current_user.es_admin_despacho():
            sucursal_id = form.sucursal_id.data
            if not sucursal_id or sucursal_id == 0:
                flash('Debes seleccionar una clínica para registrar el CFDI.', 'danger')
                return render_template('cfdi/upload.html', form=form)
        else:
            sucursal_id = current_user.sucursal_id

        # Buscar o crear proveedor
        proveedor = Proveedor.query.filter_by(rfc=datos.get('emisor_rfc')).first()
        if not proveedor:
            # Crear proveedor automáticamente
            proveedor = Proveedor(
                rfc=datos.get('emisor_rfc'),
                razon_social=datos.get('emisor_nombre', 'Sin nombre'),
                regimen_fiscal=datos.get('emisor_regimen', ''),
                sucursal_id=sucursal_id,
                activo=True
            )
            db.session.add(proveedor)
            db.session.flush()  # Para obtener el ID

        # Crear registro de factura CFDI
        factura = FacturaCFDI(
            uuid=uuid,
            version_cfdi=datos.get('version'),
            serie=datos.get('serie', ''),
            folio=datos.get('folio', ''),
            fecha_emision=datos.get('fecha_emision'),
            fecha_timbrado=datos.get('fecha_timbrado'),
            tipo_comprobante=datos.get('tipo_comprobante'),
            proveedor_id=proveedor.id,
            emisor_rfc=datos.get('emisor_rfc'),
            emisor_nombre=datos.get('emisor_nombre', ''),
            emisor_regimen=datos.get('emisor_regimen', ''),
            receptor_rfc=datos.get('receptor_rfc'),
            receptor_nombre=datos.get('receptor_nombre', ''),
            receptor_uso_cfdi=datos.get('receptor_uso_cfdi', ''),
            subtotal=datos.get('subtotal', 0),
            descuento=datos.get('descuento', 0),
            total=datos.get('total', 0),
            iva=datos.get('iva', 0),
            ieps=datos.get('ieps', 0),
            isr_retenido=datos.get('isr_retenido', 0),
            iva_retenido=datos.get('iva_retenido', 0),
            moneda=datos.get('moneda', 'MXN'),
            tipo_cambio=datos.get('tipo_cambio', 1),
            metodo_pago=datos.get('metodo_pago', ''),
            forma_pago=datos.get('forma_pago', ''),
            xml_filename=unique_filename,
            xml_path=filepath,
            sucursal_id=sucursal_id,
            notas=form.notas.data or ''
        )

        db.session.add(factura)
        db.session.flush()

        # Asociar con egreso si se seleccionó
        egreso_id = form.movimiento_id.data  # Usa el mismo campo del form
        if egreso_id and egreso_id != 0:
            egreso = Egreso.query.get(egreso_id)
            if egreso:
                factura.egreso_id = egreso.id

        db.session.commit()

        flash(f'CFDI procesado exitosamente. UUID: {uuid}', 'success')
        return redirect(url_for('cfdi.detalle', id=factura.id))

    return render_template('cfdi/upload.html',
                         form=form,
                         es_admin=current_user.es_admin_despacho(),
                         sucursal_seleccionada=sucursal_filtro_id if current_user.es_admin_despacho() else None)


@bp.route('/detalle/<int:id>')
@login_required
def detalle(id):
    """
    Mostrar detalles de una factura CFDI
    """
    factura = FacturaCFDI.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if factura.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para ver este CFDI.', 'danger')
            return redirect(url_for('cfdi.index'))

    # Formulario para asociar con egreso
    form = AsociarCFDIForm()

    # Cargar egresos disponibles (sin CFDI asociado)
    if current_user.es_admin_despacho():
        egresos = Egreso.query.outerjoin(FacturaCFDI).filter(FacturaCFDI.id == None).order_by(Egreso.fecha.desc()).limit(100).all()
    else:
        egresos = Egreso.query.outerjoin(FacturaCFDI).filter(
            FacturaCFDI.id == None,
            Egreso.sucursal_id == current_user.sucursal_id
        ).order_by(Egreso.fecha.desc()).limit(100).all()

    form.movimiento_id.choices = [
        (e.id, f'EGRESO - {e.fecha.strftime("%Y-%m-%d")} - ${e.monto:,.2f} - {e.notas[:50] if e.notas else ""}')
        for e in egresos
    ]

    return render_template('cfdi/detalle.html', factura=factura, form=form)


@bp.route('/asociar/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def asociar_movimiento(id):
    """
    Asociar CFDI con un egreso
    """
    factura = FacturaCFDI.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if factura.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para modificar este CFDI.', 'danger')
            return redirect(url_for('cfdi.index'))

    form = AsociarCFDIForm()

    # Cargar egresos disponibles (sin CFDI asociado)
    if current_user.es_admin_despacho():
        egresos = Egreso.query.outerjoin(FacturaCFDI).filter(FacturaCFDI.id == None).order_by(Egreso.fecha.desc()).limit(100).all()
    else:
        egresos = Egreso.query.outerjoin(FacturaCFDI).filter(
            FacturaCFDI.id == None,
            Egreso.sucursal_id == current_user.sucursal_id
        ).order_by(Egreso.fecha.desc()).limit(100).all()

    form.movimiento_id.choices = [
        (e.id, f'EGRESO - {e.fecha.strftime("%Y-%m-%d")} - ${e.monto:,.2f} - {e.notas[:50] if e.notas else ""}')
        for e in egresos
    ]

    if form.validate_on_submit():
        egreso_id = form.movimiento_id.data
        egreso = Egreso.query.get(egreso_id)

        if not egreso:
            flash('Egreso no encontrado.', 'danger')
            return redirect(url_for('cfdi.detalle', id=id))

        # Verificar que el egreso pertenezca a la misma clínica
        if not current_user.es_admin_despacho():
            if egreso.sucursal_id != current_user.sucursal_id:
                flash('No puedes asociar con egresos de otra clínica.', 'danger')
                return redirect(url_for('cfdi.detalle', id=id))

        # Asociar
        factura.egreso_id = egreso.id
        db.session.commit()

        flash('CFDI asociado exitosamente con el egreso.', 'success')
        return redirect(url_for('cfdi.detalle', id=id))

    return redirect(url_for('cfdi.detalle', id=id))


@bp.route('/desasociar/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def desasociar_movimiento(id):
    """
    Desasociar CFDI de un egreso
    """
    factura = FacturaCFDI.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if factura.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para modificar este CFDI.', 'danger')
            return redirect(url_for('cfdi.index'))

    if factura.egreso_id:
        factura.egreso_id = None
        db.session.commit()
        flash('CFDI desasociado del egreso.', 'success')
    else:
        flash('Este CFDI no está asociado a ningún egreso.', 'warning')

    return redirect(url_for('cfdi.detalle', id=id))


@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def eliminar(id):
    """
    Eliminar un CFDI
    """
    factura = FacturaCFDI.query.get_or_404(id)

    # Verificar permisos
    if not current_user.es_admin_despacho():
        if factura.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para eliminar este CFDI.', 'danger')
            return redirect(url_for('cfdi.index'))

    # Desasociar egreso si existe
    if factura.egreso_id:
        factura.egreso_id = None

    # Eliminar archivo físico
    if factura.xml_filename:
        try:
            filepath = os.path.join(current_app.root_path, 'uploads', 'cfdi', factura.xml_filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error eliminando archivo: {e}")

    # Eliminar registro de la base de datos
    db.session.delete(factura)
    db.session.commit()

    flash('CFDI eliminado exitosamente.', 'success')
    return redirect(url_for('cfdi.index'))
