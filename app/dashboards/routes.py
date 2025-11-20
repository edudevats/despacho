"""
Rutas de Dashboards
Dashboards jerárquicos para despacho, organizaciones y sucursales
"""
from flask import render_template, jsonify
from flask_login import login_required, current_user
from app.dashboards import bp
from app.auth.decoradores import admin_despacho_required, login_required_with_role
from app.models import Organizacion, Sucursal, Ingreso, Egreso, Usuario, db
from sqlalchemy import func, extract
from datetime import datetime, date
from decimal import Decimal


@bp.route('/despacho')
@login_required
@admin_despacho_required
def despacho():
    """
    Dashboard principal del despacho contable
    Vista filtrable por organización
    """
    from flask import request

    # Obtener organización seleccionada del query string
    organizacion_id = request.args.get('organizacion_id', type=int)

    # Obtener todas las organizaciones para el selector
    todas_organizaciones = Organizacion.query.filter_by(activa=True).order_by(Organizacion.nombre).all()
    organizacion_seleccionada = None

    # Determinar qué sucursales filtrar
    if organizacion_id:
        # Filtrar por organización específica
        organizacion_seleccionada = Organizacion.query.get(organizacion_id)
        sucursales_filtradas = Sucursal.query.filter_by(organizacion_id=organizacion_id).all()
        sucursales_ids = [s.id for s in sucursales_filtradas]
    else:
        # Todas las sucursales
        sucursales_filtradas = Sucursal.query.all()
        sucursales_ids = [s.id for s in sucursales_filtradas]

    # Totales (filtrados por organización si aplica)
    if sucursales_ids:
        total_ingresos = db.session.query(func.sum(Ingreso.monto)).filter(
            Ingreso.sucursal_id.in_(sucursales_ids)
        ).scalar() or Decimal('0.00')

        total_egresos = db.session.query(func.sum(Egreso.monto)).filter(
            Egreso.sucursal_id.in_(sucursales_ids)
        ).scalar() or Decimal('0.00')
    else:
        total_ingresos = Decimal('0.00')
        total_egresos = Decimal('0.00')

    balance = total_ingresos - total_egresos

    totales = {
        'ingresos': float(total_ingresos),
        'egresos': float(total_egresos),
        'balance': float(balance)
    }

    # Comparativo por sucursal de la organización seleccionada
    comparativo_suc = []

    for suc in sucursales_filtradas:
        if suc.activa:
            ingresos = db.session.query(func.sum(Ingreso.monto)).filter_by(
                sucursal_id=suc.id
            ).scalar() or Decimal('0.00')

            egresos = db.session.query(func.sum(Egreso.monto)).filter_by(
                sucursal_id=suc.id
            ).scalar() or Decimal('0.00')

            comparativo_suc.append({
                'nombre': suc.nombre,
                'organizacion': suc.organizacion.nombre,
                'ingresos': float(ingresos),
                'egresos': float(egresos),
                'balance': float(ingresos - egresos)
            })

    # Ordenar por balance
    comparativo_suc.sort(key=lambda x: x['balance'], reverse=True)

    # Resumen mensual (últimos 6 meses) filtrado
    resumen_mensual = []
    hoy = datetime.now()

    for i in range(5, -1, -1):  # 6 meses atrás hasta hoy
        mes = hoy.month - i
        año = hoy.year

        if mes <= 0:
            mes += 12
            año -= 1

        if sucursales_ids:
            ingresos = db.session.query(func.sum(Ingreso.monto)).filter(
                Ingreso.sucursal_id.in_(sucursales_ids),
                extract('month', Ingreso.fecha) == mes,
                extract('year', Ingreso.fecha) == año
            ).scalar() or Decimal('0.00')

            egresos = db.session.query(func.sum(Egreso.monto)).filter(
                Egreso.sucursal_id.in_(sucursales_ids),
                extract('month', Egreso.fecha) == mes,
                extract('year', Egreso.fecha) == año
            ).scalar() or Decimal('0.00')
        else:
            ingresos = Decimal('0.00')
            egresos = Decimal('0.00')

        nombre_mes = datetime(año, mes, 1).strftime('%B')

        resumen_mensual.append({
            'mes': nombre_mes.capitalize(),
            'ingresos': float(ingresos),
            'egresos': float(egresos)
        })

    return render_template(
        'dashboards/despacho.html',
        totales=totales,
        comparativo_suc=comparativo_suc,
        resumen_mensual=resumen_mensual,
        todas_organizaciones=todas_organizaciones,
        organizacion_seleccionada=organizacion_seleccionada,
        num_sucursales=len(sucursales_filtradas)
    )


@bp.route('/organizacion')
@login_required
@login_required_with_role('principal_organizacion')
def organizacion():
    """
    Dashboard de la organización
    Comparativo de todas las sucursales de la organización
    """
    organizacion_id = current_user.organizacion_id

    # Totales de la organización
    sucursales_ids = [s.id for s in Sucursal.query.filter_by(organizacion_id=organizacion_id).all()]

    if sucursales_ids:
        total_ingresos = db.session.query(func.sum(Ingreso.monto)).filter(
            Ingreso.sucursal_id.in_(sucursales_ids)
        ).scalar() or Decimal('0.00')

        total_egresos = db.session.query(func.sum(Egreso.monto)).filter(
            Egreso.sucursal_id.in_(sucursales_ids)
        ).scalar() or Decimal('0.00')
    else:
        total_ingresos = Decimal('0.00')
        total_egresos = Decimal('0.00')

    totales = {
        'ingresos': float(total_ingresos),
        'egresos': float(total_egresos),
        'balance': float(total_ingresos - total_egresos)
    }

    # Comparativo por sucursal
    sucursales = Sucursal.query.filter_by(organizacion_id=organizacion_id, activa=True).all()
    comparativo_sucursales = []

    for suc in sucursales:
        ingresos = db.session.query(func.sum(Ingreso.monto)).filter_by(
            sucursal_id=suc.id
        ).scalar() or Decimal('0.00')

        egresos = db.session.query(func.sum(Egreso.monto)).filter_by(
            sucursal_id=suc.id
        ).scalar() or Decimal('0.00')

        # Usuarios activos en la sucursal
        usuarios_activos = Usuario.query.filter_by(sucursal_id=suc.id, activo=True).count()

        comparativo_sucursales.append({
            'id': suc.id,
            'nombre': suc.nombre,
            'ingresos': float(ingresos),
            'egresos': float(egresos),
            'balance': float(ingresos - egresos),
            'usuarios': usuarios_activos
        })

    # Resumen mensual de la organización (últimos 3 meses)
    resumen_mensual = []
    hoy = datetime.now()

    for i in range(2, -1, -1):
        mes = hoy.month - i
        año = hoy.year

        if mes <= 0:
            mes += 12
            año -= 1

        if sucursales_ids:
            ingresos = db.session.query(func.sum(Ingreso.monto)).filter(
                Ingreso.sucursal_id.in_(sucursales_ids),
                extract('month', Ingreso.fecha) == mes,
                extract('year', Ingreso.fecha) == año
            ).scalar() or Decimal('0.00')

            egresos = db.session.query(func.sum(Egreso.monto)).filter(
                Egreso.sucursal_id.in_(sucursales_ids),
                extract('month', Egreso.fecha) == mes,
                extract('year', Egreso.fecha) == año
            ).scalar() or Decimal('0.00')
        else:
            ingresos = Decimal('0.00')
            egresos = Decimal('0.00')

        nombre_mes = datetime(año, mes, 1).strftime('%B')

        resumen_mensual.append({
            'mes': nombre_mes.capitalize(),
            'ingresos': float(ingresos),
            'egresos': float(egresos)
        })

    # Top categorías de ingreso en la organización
    from app.models import CategoriaIngreso

    top_categorias = []
    if sucursales_ids:
        distribucion = db.session.query(
            CategoriaIngreso.nombre,
            func.sum(Ingreso.monto).label('total')
        ).join(Ingreso).filter(
            Ingreso.sucursal_id.in_(sucursales_ids)
        ).group_by(CategoriaIngreso.nombre).order_by(func.sum(Ingreso.monto).desc()).limit(5).all()

        top_categorias = [
            {'categoria': cat, 'total': float(total)}
            for cat, total in distribucion
        ]

    organizacion = Organizacion.query.get(organizacion_id)

    return render_template(
        'dashboards/organizacion.html',
        organizacion=organizacion,
        totales=totales,
        comparativo_sucursales=comparativo_sucursales,
        resumen_mensual=resumen_mensual,
        top_categorias=top_categorias,
        num_sucursales=len(sucursales)
    )


@bp.route('/sucursal')
@login_required
@login_required_with_role('principal_sucursal', 'secundario_pos')
def sucursal():
    """
    Dashboard de la sucursal
    Métricas detalladas de la sucursal del usuario
    """
    sucursal_id = current_user.sucursal_id

    if not sucursal_id:
        from flask import flash, redirect, url_for
        flash('No tienes una sucursal asignada.', 'warning')
        return redirect(url_for('main.index'))

    sucursal = Sucursal.query.get(sucursal_id)

    # Totales del día
    hoy = date.today()

    ingresos_hoy = db.session.query(func.sum(Ingreso.monto)).filter(
        Ingreso.sucursal_id == sucursal_id,
        Ingreso.fecha == hoy
    ).scalar() or Decimal('0.00')

    egresos_hoy = db.session.query(func.sum(Egreso.monto)).filter(
        Egreso.sucursal_id == sucursal_id,
        Egreso.fecha == hoy
    ).scalar() or Decimal('0.00')

    totales_hoy = {
        'ingresos': float(ingresos_hoy),
        'egresos': float(egresos_hoy),
        'balance': float(ingresos_hoy - egresos_hoy)
    }

    # Totales del mes
    mes_actual = datetime.now().month
    año_actual = datetime.now().year

    ingresos_mes = db.session.query(func.sum(Ingreso.monto)).filter(
        Ingreso.sucursal_id == sucursal_id,
        extract('month', Ingreso.fecha) == mes_actual,
        extract('year', Ingreso.fecha) == año_actual
    ).scalar() or Decimal('0.00')

    egresos_mes = db.session.query(func.sum(Egreso.monto)).filter(
        Egreso.sucursal_id == sucursal_id,
        extract('month', Egreso.fecha) == mes_actual,
        extract('year', Egreso.fecha) == año_actual
    ).scalar() or Decimal('0.00')

    totales_mes = {
        'ingresos': float(ingresos_mes),
        'egresos': float(egresos_mes),
        'balance': float(ingresos_mes - egresos_mes)
    }

    # Totales históricos
    total_ingresos = db.session.query(func.sum(Ingreso.monto)).filter_by(
        sucursal_id=sucursal_id
    ).scalar() or Decimal('0.00')

    total_egresos = db.session.query(func.sum(Egreso.monto)).filter_by(
        sucursal_id=sucursal_id
    ).scalar() or Decimal('0.00')

    totales_historicos = {
        'ingresos': float(total_ingresos),
        'egresos': float(total_egresos),
        'balance': float(total_ingresos - total_egresos)
    }

    # Distribución por categorías (para gráfica de pastel)
    from app.models import CategoriaIngreso

    distribucion = db.session.query(
        CategoriaIngreso.nombre,
        func.sum(Ingreso.monto).label('total')
    ).join(Ingreso).filter(
        Ingreso.sucursal_id == sucursal_id
    ).group_by(CategoriaIngreso.nombre).all()

    distribucion_categorias = [
        {'categoria': cat, 'total': float(total)}
        for cat, total in distribucion
    ]

    # Movimientos por usuario
    usuarios = Usuario.query.filter_by(sucursal_id=sucursal_id, activo=True).all()
    movimientos_usuario = []

    for usuario in usuarios:
        ingresos_usuario = db.session.query(func.sum(Ingreso.monto)).filter_by(
            usuario_id=usuario.id
        ).scalar() or Decimal('0.00')

        num_movimientos = Ingreso.query.filter_by(usuario_id=usuario.id).count()
        num_movimientos += Egreso.query.filter_by(usuario_id=usuario.id).count()

        movimientos_usuario.append({
            'nombre': usuario.nombre_completo or usuario.username,
            'ingresos': float(ingresos_usuario),
            'num_movimientos': num_movimientos
        })

    # Últimos movimientos (combinados)
    ultimos_movimientos = []

    ingresos_recientes = Ingreso.query.filter_by(sucursal_id=sucursal_id).order_by(
        Ingreso.fecha_registro.desc()
    ).limit(5).all()

    for ing in ingresos_recientes:
        ultimos_movimientos.append({
            'tipo': 'ingreso',
            'fecha': ing.fecha,
            'categoria': ing.categoria.nombre,
            'monto': float(ing.monto),
            'usuario': ing.usuario_registro.nombre_completo
        })

    egresos_recientes = Egreso.query.filter_by(sucursal_id=sucursal_id).order_by(
        Egreso.fecha_registro.desc()
    ).limit(5).all()

    for egr in egresos_recientes:
        ultimos_movimientos.append({
            'tipo': 'egreso',
            'fecha': egr.fecha,
            'categoria': egr.categoria.nombre,
            'monto': float(egr.monto),
            'usuario': egr.usuario_registro.nombre_completo
        })

    # Ordenar por fecha de registro
    ultimos_movimientos.sort(key=lambda x: x['fecha'], reverse=True)

    # Resumen mensual de la sucursal (últimos 6 meses)
    resumen_mensual = []
    hoy = datetime.now()

    for i in range(5, -1, -1):
        mes = hoy.month - i
        año = hoy.year

        if mes <= 0:
            mes += 12
            año -= 1

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

        nombre_mes = datetime(año, mes, 1).strftime('%B')

        resumen_mensual.append({
            'mes': nombre_mes.capitalize(),
            'ingresos': float(ingresos),
            'egresos': float(egresos)
        })

    return render_template(
        'dashboards/sucursal.html',
        sucursal=sucursal,
        totales_hoy=totales_hoy,
        totales_mes=totales_mes,
        totales_historicos=totales_historicos,
        distribucion_categorias=distribucion_categorias,
        movimientos_usuario=movimientos_usuario,
        ultimos_movimientos=ultimos_movimientos[:10],
        resumen_mensual=resumen_mensual
    )


@bp.route('/')
@login_required
def index():
    """
    Redirige al dashboard apropiado según el rol del usuario
    """
    from flask import redirect, url_for

    if current_user.es_admin_despacho():
        return redirect(url_for('dashboards.despacho'))
    elif current_user.es_principal_organizacion():
        return redirect(url_for('dashboards.organizacion'))
    else:
        return redirect(url_for('dashboards.sucursal'))
