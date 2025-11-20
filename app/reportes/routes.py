"""
Rutas de Reportes
Generación de reportes PDF y Excel con jerarquía de 4 niveles
"""
from flask import render_template, send_file, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.reportes import bp
from app.auth.decoradores import permiso_ver_reportes_required, login_required_with_role
from app.models import Sucursal, Organizacion, Ingreso, Egreso, CategoriaIngreso, CategoriaEgreso, Usuario, db
from sqlalchemy import func, extract, desc
from datetime import datetime, date
from decimal import Decimal
import os


@bp.route('/')
@login_required
@permiso_ver_reportes_required
def index():
    """
    Pantalla de selección de reportes
    """
    # Obtener sucursales disponibles según el rol
    if current_user.es_admin_despacho():
        sucursales = Sucursal.query.filter_by(activa=True).all()
        organizaciones = Organizacion.query.filter_by(activa=True).all()
    elif current_user.es_principal_organizacion():
        sucursales = Sucursal.query.filter_by(
            organizacion_id=current_user.organizacion_id,
            activa=True
        ).all()
        organizaciones = [Organizacion.query.get(current_user.organizacion_id)]
    else:
        sucursales = [Sucursal.query.get(current_user.sucursal_id)]
        organizaciones = [Organizacion.query.get(current_user.organizacion_id)]

    return render_template('reportes/index.html',
                         sucursales=sucursales,
                         organizaciones=organizaciones,
                         fecha_actual=datetime.now())


@bp.route('/generar/pdf')
@login_required
@permiso_ver_reportes_required
def generar_pdf():
    """
    Genera reporte mensual en PDF para una sucursal
    """
    sucursal_id = request.args.get('sucursal_id', type=int)
    mes = request.args.get('mes', type=int)
    año = request.args.get('año', type=int, default=datetime.now().year)

    if not sucursal_id or not mes:
        flash('Debe seleccionar sucursal y mes para generar el reporte.', 'warning')
        return redirect(url_for('reportes.index'))

    # Verificar permisos
    sucursal = Sucursal.query.get_or_404(sucursal_id)

    if current_user.es_principal_organizacion():
        if sucursal.organizacion_id != current_user.organizacion_id:
            flash('No puedes generar reportes de otra organización.', 'danger')
            return redirect(url_for('reportes.index'))
    elif not current_user.es_admin_despacho():
        if sucursal_id != current_user.sucursal_id:
            flash('No puedes generar reportes de otra sucursal.', 'danger')
            return redirect(url_for('reportes.index'))

    # Preparar datos del reporte
    datos_reporte = preparar_datos_reporte(sucursal_id, mes, año)

    # Generar PDF
    from app.reportes.pdf_generator import generar_reporte_mensual_pdf

    buffer = generar_reporte_mensual_pdf(sucursal, mes, año, datos_reporte)

    filename = f"reporte_{sucursal.nombre}_{año}_{mes:02d}.pdf"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )


@bp.route('/generar/pdf_organizacion')
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion')
def generar_pdf_organizacion():
    """
    Genera reporte consolidado de organización (todas las sucursales)
    """
    organizacion_id = request.args.get('organizacion_id', type=int)
    mes = request.args.get('mes', type=int)
    año = request.args.get('año', type=int, default=datetime.now().year)

    if not organizacion_id or not mes:
        flash('Debe seleccionar organización y mes para generar el reporte.', 'warning')
        return redirect(url_for('reportes.index'))

    organizacion = Organizacion.query.get_or_404(organizacion_id)

    # Verificar permisos
    if current_user.es_principal_organizacion():
        if organizacion_id != current_user.organizacion_id:
            flash('No puedes generar reportes de otra organización.', 'danger')
            return redirect(url_for('reportes.index'))

    # Obtener todas las sucursales de la organización
    sucursales = Sucursal.query.filter_by(organizacion_id=organizacion_id).all()
    sucursales_ids = [s.id for s in sucursales]

    # Preparar datos consolidados
    datos_reporte = preparar_datos_reporte_organizacion(sucursales_ids, mes, año, sucursales)

    # Generar PDF consolidado
    from app.reportes.pdf_generator import generar_reporte_organizacion_pdf

    buffer = generar_reporte_organizacion_pdf(organizacion, mes, año, datos_reporte)

    filename = f"reporte_consolidado_{organizacion.nombre}_{año}_{mes:02d}.pdf"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )


def preparar_datos_reporte(sucursal_id, mes, año):
    """
    Prepara los datos necesarios para el reporte de una sucursal
    """
    # Totales del mes
    total_ingresos = db.session.query(func.sum(Ingreso.monto)).filter(
        Ingreso.sucursal_id == sucursal_id,
        extract('month', Ingreso.fecha) == mes,
        extract('year', Ingreso.fecha) == año
    ).scalar() or Decimal('0.00')

    total_egresos = db.session.query(func.sum(Egreso.monto)).filter(
        Egreso.sucursal_id == sucursal_id,
        extract('month', Egreso.fecha) == mes,
        extract('year', Egreso.fecha) == año
    ).scalar() or Decimal('0.00')

    balance_neto = total_ingresos - total_egresos
    margen = (balance_neto / total_ingresos * 100) if total_ingresos > 0 else 0

    # Desglose por categorías de ingresos
    desglose_ingresos = db.session.query(
        CategoriaIngreso.nombre,
        func.sum(Ingreso.monto).label('total')
    ).join(Ingreso).filter(
        Ingreso.sucursal_id == sucursal_id,
        extract('month', Ingreso.fecha) == mes,
        extract('year', Ingreso.fecha) == año
    ).group_by(CategoriaIngreso.nombre).all()

    # Desglose por categorías de egresos
    desglose_egresos = db.session.query(
        CategoriaEgreso.nombre,
        func.sum(Egreso.monto).label('total')
    ).join(Egreso).filter(
        Egreso.sucursal_id == sucursal_id,
        extract('month', Egreso.fecha) == mes,
        extract('year', Egreso.fecha) == año
    ).group_by(CategoriaEgreso.nombre).all()

    # Comparativo mes anterior
    mes_anterior = mes - 1 if mes > 1 else 12
    año_anterior = año if mes > 1 else año - 1

    ingresos_mes_anterior = db.session.query(func.sum(Ingreso.monto)).filter(
        Ingreso.sucursal_id == sucursal_id,
        extract('month', Ingreso.fecha) == mes_anterior,
        extract('year', Ingreso.fecha) == año_anterior
    ).scalar() or Decimal('0.01')

    egresos_mes_anterior = db.session.query(func.sum(Egreso.monto)).filter(
        Egreso.sucursal_id == sucursal_id,
        extract('month', Egreso.fecha) == mes_anterior,
        extract('year', Egreso.fecha) == año_anterior
    ).scalar() or Decimal('0.01')

    cambio_ingresos = ((total_ingresos - ingresos_mes_anterior) / ingresos_mes_anterior * 100)
    cambio_egresos = ((total_egresos - egresos_mes_anterior) / egresos_mes_anterior * 100)

    return {
        'total_ingresos': float(total_ingresos),
        'total_egresos': float(total_egresos),
        'balance_neto': float(balance_neto),
        'margen': float(margen),
        'desglose_ingresos': [{'nombre': n, 'total': float(t)} for n, t in desglose_ingresos],
        'desglose_egresos': [{'nombre': n, 'total': float(t)} for n, t in desglose_egresos],
        'comparativo_mes_anterior': {
            'ingresos_cambio': float(cambio_ingresos),
            'egresos_cambio': float(cambio_egresos)
        },
        'observaciones': []
    }


def preparar_datos_reporte_organizacion(sucursales_ids, mes, año, sucursales):
    """
    Prepara los datos consolidados de todas las sucursales de una organización
    """
    if not sucursales_ids:
        return {
            'total_ingresos': 0.0,
            'total_egresos': 0.0,
            'balance_neto': 0.0,
            'margen': 0.0,
            'desglose_ingresos': [],
            'desglose_egresos': [],
            'comparativo_sucursales': [],
            'comparativo_mes_anterior': {'ingresos_cambio': 0.0, 'egresos_cambio': 0.0},
            'observaciones': []
        }

    # Totales consolidados del mes
    total_ingresos = db.session.query(func.sum(Ingreso.monto)).filter(
        Ingreso.sucursal_id.in_(sucursales_ids),
        extract('month', Ingreso.fecha) == mes,
        extract('year', Ingreso.fecha) == año
    ).scalar() or Decimal('0.00')

    total_egresos = db.session.query(func.sum(Egreso.monto)).filter(
        Egreso.sucursal_id.in_(sucursales_ids),
        extract('month', Egreso.fecha) == mes,
        extract('year', Egreso.fecha) == año
    ).scalar() or Decimal('0.00')

    balance_neto = total_ingresos - total_egresos
    margen = (balance_neto / total_ingresos * 100) if total_ingresos > 0 else 0

    # Desglose por categorías consolidadas
    desglose_ingresos = db.session.query(
        CategoriaIngreso.nombre,
        func.sum(Ingreso.monto).label('total')
    ).join(Ingreso).filter(
        Ingreso.sucursal_id.in_(sucursales_ids),
        extract('month', Ingreso.fecha) == mes,
        extract('year', Ingreso.fecha) == año
    ).group_by(CategoriaIngreso.nombre).all()

    desglose_egresos = db.session.query(
        CategoriaEgreso.nombre,
        func.sum(Egreso.monto).label('total')
    ).join(Egreso).filter(
        Egreso.sucursal_id.in_(sucursales_ids),
        extract('month', Egreso.fecha) == mes,
        extract('year', Egreso.fecha) == año
    ).group_by(CategoriaEgreso.nombre).all()

    # Comparativo por sucursal
    comparativo_sucursales = []
    for suc in sucursales:
        ing = db.session.query(func.sum(Ingreso.monto)).filter(
            Ingreso.sucursal_id == suc.id,
            extract('month', Ingreso.fecha) == mes,
            extract('year', Ingreso.fecha) == año
        ).scalar() or Decimal('0.00')

        egr = db.session.query(func.sum(Egreso.monto)).filter(
            Egreso.sucursal_id == suc.id,
            extract('month', Egreso.fecha) == mes,
            extract('year', Egreso.fecha) == año
        ).scalar() or Decimal('0.00')

        comparativo_sucursales.append({
            'nombre': suc.nombre,
            'ingresos': float(ing),
            'egresos': float(egr),
            'balance': float(ing - egr)
        })

    # Comparativo mes anterior
    mes_anterior = mes - 1 if mes > 1 else 12
    año_anterior = año if mes > 1 else año - 1

    ingresos_mes_anterior = db.session.query(func.sum(Ingreso.monto)).filter(
        Ingreso.sucursal_id.in_(sucursales_ids),
        extract('month', Ingreso.fecha) == mes_anterior,
        extract('year', Ingreso.fecha) == año_anterior
    ).scalar() or Decimal('0.01')

    egresos_mes_anterior = db.session.query(func.sum(Egreso.monto)).filter(
        Egreso.sucursal_id.in_(sucursales_ids),
        extract('month', Egreso.fecha) == mes_anterior,
        extract('year', Egreso.fecha) == año_anterior
    ).scalar() or Decimal('0.01')

    cambio_ingresos = ((total_ingresos - ingresos_mes_anterior) / ingresos_mes_anterior * 100)
    cambio_egresos = ((total_egresos - egresos_mes_anterior) / egresos_mes_anterior * 100)

    return {
        'total_ingresos': float(total_ingresos),
        'total_egresos': float(total_egresos),
        'balance_neto': float(balance_neto),
        'margen': float(margen),
        'desglose_ingresos': [{'nombre': n, 'total': float(t)} for n, t in desglose_ingresos],
        'desglose_egresos': [{'nombre': n, 'total': float(t)} for n, t in desglose_egresos],
        'comparativo_sucursales': comparativo_sucursales,
        'comparativo_mes_anterior': {
            'ingresos_cambio': float(cambio_ingresos),
            'egresos_cambio': float(cambio_egresos)
        },
        'observaciones': []
    }


@bp.route('/sucursal/<int:sucursal_id>')
@login_required
@permiso_ver_reportes_required
def ver_sucursal(sucursal_id):
    """
    Ver reportes históricos de una sucursal
    """
    sucursal = Sucursal.query.get_or_404(sucursal_id)

    # Verificar permisos
    if current_user.es_principal_organizacion():
        if sucursal.organizacion_id != current_user.organizacion_id:
            flash('No puedes ver reportes de otra organización.', 'danger')
            return redirect(url_for('reportes.index'))
    elif not current_user.es_admin_despacho():
        if sucursal_id != current_user.sucursal_id:
            flash('No puedes ver reportes de otra sucursal.', 'danger')
            return redirect(url_for('reportes.index'))

    # Obtener resumen de movimientos por mes (últimos 12 meses)
    from dateutil.relativedelta import relativedelta

    hoy = datetime.now()
    resumen_meses = []

    for i in range(11, -1, -1):
        fecha = hoy - relativedelta(months=i)
        mes = fecha.month
        año = fecha.year

        ingresos = db.session.query(func.sum(Ingreso.monto)).filter(
            Ingreso.sucursal_id == sucursal_id,
            extract('month', Ingreso.fecha) == mes,
            extract('year', Ingreso.fecha) == año
        ).scalar() or Decimal('0.00')

        egresos = db.session.query(func.sum(Egreso.monto)).filter(
            Egreso.sucursal_id == sucursal_id,
            extract('month', Egreso.fecha) == mes,
            extract('year', Egreso.fecha) == año
        ).scalar() or Decimal('0.00')

        resumen_meses.append({
            'mes': mes,
            'año': año,
            'mes_nombre': fecha.strftime('%B %Y'),
            'ingresos': float(ingresos),
            'egresos': float(egresos),
            'balance': float(ingresos - egresos)
        })

    return render_template('reportes/sucursal.html',
                         sucursal=sucursal,
                         resumen_meses=resumen_meses)
