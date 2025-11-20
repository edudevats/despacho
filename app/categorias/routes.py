"""
Rutas de Categorías
Gestión de categorías de ingresos y egresos (organizacionales y por sucursal)
"""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.categorias import bp
from app.categorias.forms import CategoriaForm
from app.auth.decoradores import login_required_with_role
from app.auth.auditoria import registrar_auditoria
from app.models import CategoriaIngreso, CategoriaEgreso, Ingreso, Egreso, db


@bp.route('/')
@login_required
@login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
def index():
    """
    Listado de categorías
    - Admin: ve todo (no debería editar)
    - Director organización: ve org + todas sucursales
    - Gerente sucursal: ve org + su sucursal
    """
    if current_user.es_admin_despacho():
        # Admin ve todas (para referencia, no puede editar)
        categorias_ingreso_org = CategoriaIngreso.query.filter(
            CategoriaIngreso.organizacion_id.isnot(None)
        ).order_by(CategoriaIngreso.nombre).all()

        categorias_ingreso_suc = CategoriaIngreso.query.filter(
            CategoriaIngreso.sucursal_id.isnot(None)
        ).order_by(CategoriaIngreso.nombre).all()

        categorias_egreso_org = CategoriaEgreso.query.filter(
            CategoriaEgreso.organizacion_id.isnot(None)
        ).order_by(CategoriaEgreso.nombre).all()

        categorias_egreso_suc = CategoriaEgreso.query.filter(
            CategoriaEgreso.sucursal_id.isnot(None)
        ).order_by(CategoriaEgreso.nombre).all()

    elif current_user.es_principal_organizacion():
        # Director ve categorías de su organización y de todas sus sucursales
        categorias_ingreso_org = CategoriaIngreso.query.filter_by(
            organizacion_id=current_user.organizacion_id, activa=True
        ).order_by(CategoriaIngreso.nombre).all()

        # Categorías de todas las sucursales de la organización
        from app.models import Sucursal
        sucursales_ids = [s.id for s in Sucursal.query.filter_by(organizacion_id=current_user.organizacion_id).all()]
        categorias_ingreso_suc = CategoriaIngreso.query.filter(
            CategoriaIngreso.sucursal_id.in_(sucursales_ids),
            CategoriaIngreso.activa == True
        ).order_by(CategoriaIngreso.nombre).all() if sucursales_ids else []

        categorias_egreso_org = CategoriaEgreso.query.filter_by(
            organizacion_id=current_user.organizacion_id, activa=True
        ).order_by(CategoriaEgreso.nombre).all()

        categorias_egreso_suc = CategoriaEgreso.query.filter(
            CategoriaEgreso.sucursal_id.in_(sucursales_ids),
            CategoriaEgreso.activa == True
        ).order_by(CategoriaEgreso.nombre).all() if sucursales_ids else []

    else:  # Gerente de sucursal
        # Ve categorías de su organización + de su sucursal
        categorias_ingreso_org = CategoriaIngreso.query.filter_by(
            organizacion_id=current_user.organizacion_id, activa=True
        ).order_by(CategoriaIngreso.nombre).all()

        categorias_ingreso_suc = CategoriaIngreso.query.filter_by(
            sucursal_id=current_user.sucursal_id, activa=True
        ).order_by(CategoriaIngreso.nombre).all()

        categorias_egreso_org = CategoriaEgreso.query.filter_by(
            organizacion_id=current_user.organizacion_id, activa=True
        ).order_by(CategoriaEgreso.nombre).all()

        categorias_egreso_suc = CategoriaEgreso.query.filter_by(
            sucursal_id=current_user.sucursal_id, activa=True
        ).order_by(CategoriaEgreso.nombre).all()

    return render_template('categorias/index.html',
                         categorias_ingreso_org=categorias_ingreso_org,
                         categorias_ingreso_suc=categorias_ingreso_suc,
                         categorias_egreso_org=categorias_egreso_org,
                         categorias_egreso_suc=categorias_egreso_suc)


# ==================== CATEGORÍAS DE INGRESO ====================

@bp.route('/ingreso/nueva', methods=['GET', 'POST'])
@login_required
@login_required_with_role('principal_organizacion', 'principal_sucursal')
def nueva_ingreso():
    """
    Crear nueva categoría de ingreso
    - Director organización: crea a nivel organización (compartida)
    - Gerente sucursal: crea a nivel sucursal (específica)
    """
    form = CategoriaForm()
    nivel = request.args.get('nivel', 'sucursal')  # organizacion o sucursal

    if form.validate_on_submit():
        # Determinar si es organizacional o de sucursal
        if current_user.es_principal_organizacion() and nivel == 'organizacion':
            # Verificar que no exista en la organización
            existe = CategoriaIngreso.query.filter_by(
                organizacion_id=current_user.organizacion_id,
                nombre=form.nombre.data
            ).first()

            if existe:
                flash(f'Ya existe una categoría organizacional de ingreso con el nombre "{form.nombre.data}".', 'warning')
                return render_template('categorias/formulario.html', form=form, tipo='ingreso', accion='nueva', nivel=nivel)

            # Crear categoría organizacional
            categoria = CategoriaIngreso(
                organizacion_id=current_user.organizacion_id,
                sucursal_id=None,
                nombre=form.nombre.data,
                descripcion=form.descripcion.data,
                activa=form.activa.data
            )

            nivel_texto = 'organización'
        else:
            # Crear categoría de sucursal
            existe = CategoriaIngreso.query.filter_by(
                sucursal_id=current_user.sucursal_id,
                nombre=form.nombre.data
            ).first()

            if existe:
                flash(f'Ya existe una categoría de sucursal de ingreso con el nombre "{form.nombre.data}".', 'warning')
                return render_template('categorias/formulario.html', form=form, tipo='ingreso', accion='nueva', nivel=nivel)

            categoria = CategoriaIngreso(
                organizacion_id=None,
                sucursal_id=current_user.sucursal_id,
                nombre=form.nombre.data,
                descripcion=form.descripcion.data,
                activa=form.activa.data
            )

            nivel_texto = 'sucursal'

        db.session.add(categoria)
        db.session.commit()

        registrar_auditoria('create', 'categoria_ingreso', categoria.id, {
            'nombre': categoria.nombre,
            'nivel': nivel_texto,
            'organizacion_id': categoria.organizacion_id,
            'sucursal_id': categoria.sucursal_id
        })

        flash(f'Categoría de ingreso "{categoria.nombre}" creada exitosamente a nivel {nivel_texto}.', 'success')
        return redirect(url_for('categorias.index'))

    return render_template('categorias/formulario.html', form=form, tipo='ingreso', accion='nueva', nivel=nivel)


@bp.route('/ingreso/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@login_required_with_role('principal_organizacion', 'principal_sucursal')
def editar_ingreso(id):
    """
    Editar categoría de ingreso
    """
    categoria = CategoriaIngreso.query.get_or_404(id)

    # Verificar permisos
    if categoria.organizacion_id:
        # Categoría organizacional - solo director de esa organización
        if not current_user.es_principal_organizacion() or categoria.organizacion_id != current_user.organizacion_id:
            flash('No tienes permiso para editar esta categoría organizacional.', 'danger')
            return redirect(url_for('categorias.index'))
        nivel = 'organizacion'
    else:
        # Categoría de sucursal - solo gerente de esa sucursal o director de la org
        if current_user.es_principal_organizacion():
            # Verificar que la sucursal pertenezca a su organización
            from app.models import Sucursal
            sucursal = Sucursal.query.get(categoria.sucursal_id)
            if not sucursal or sucursal.organizacion_id != current_user.organizacion_id:
                flash('No tienes permiso para editar esta categoría.', 'danger')
                return redirect(url_for('categorias.index'))
        elif categoria.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para editar esta categoría.', 'danger')
            return redirect(url_for('categorias.index'))
        nivel = 'sucursal'

    form = CategoriaForm(obj=categoria)

    if form.validate_on_submit():
        # Verificar que no exista otra categoría con el mismo nombre en el mismo nivel
        if nivel == 'organizacion':
            existe = CategoriaIngreso.query.filter(
                CategoriaIngreso.organizacion_id == categoria.organizacion_id,
                CategoriaIngreso.nombre == form.nombre.data,
                CategoriaIngreso.id != id
            ).first()
        else:
            existe = CategoriaIngreso.query.filter(
                CategoriaIngreso.sucursal_id == categoria.sucursal_id,
                CategoriaIngreso.nombre == form.nombre.data,
                CategoriaIngreso.id != id
            ).first()

        if existe:
            flash(f'Ya existe otra categoría de ingreso con el nombre "{form.nombre.data}".', 'warning')
            return render_template('categorias/formulario.html', form=form, tipo='ingreso', accion='editar', categoria=categoria, nivel=nivel)

        # Actualizar la categoría
        nombre_anterior = categoria.nombre
        categoria.nombre = form.nombre.data
        categoria.descripcion = form.descripcion.data
        categoria.activa = form.activa.data

        db.session.commit()

        registrar_auditoria('update', 'categoria_ingreso', categoria.id, {
            'nombre_anterior': nombre_anterior,
            'nombre_nuevo': categoria.nombre
        })

        flash(f'Categoría de ingreso "{categoria.nombre}" actualizada exitosamente.', 'success')
        return redirect(url_for('categorias.index'))

    return render_template('categorias/formulario.html', form=form, tipo='ingreso', accion='editar', categoria=categoria, nivel=nivel)


@bp.route('/ingreso/eliminar/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('principal_organizacion', 'principal_sucursal')
def eliminar_ingreso(id):
    """
    Eliminar categoría de ingreso
    """
    categoria = CategoriaIngreso.query.get_or_404(id)

    # Verificar permisos
    if categoria.organizacion_id:
        if not current_user.es_principal_organizacion() or categoria.organizacion_id != current_user.organizacion_id:
            flash('No tienes permiso para eliminar esta categoría.', 'danger')
            return redirect(url_for('categorias.index'))
    else:
        if current_user.es_principal_organizacion():
            from app.models import Sucursal
            sucursal = Sucursal.query.get(categoria.sucursal_id)
            if not sucursal or sucursal.organizacion_id != current_user.organizacion_id:
                flash('No tienes permiso para eliminar esta categoría.', 'danger')
                return redirect(url_for('categorias.index'))
        elif categoria.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para eliminar esta categoría.', 'danger')
            return redirect(url_for('categorias.index'))

    # Verificar si hay ingresos asociados
    ingresos_count = Ingreso.query.filter_by(categoria_id=id).count()

    if ingresos_count > 0:
        flash(f'No se puede eliminar la categoría "{categoria.nombre}" porque tiene {ingresos_count} ingreso(s) asociado(s). Puedes desactivarla en su lugar.', 'warning')
        return redirect(url_for('categorias.index'))

    # Eliminar la categoría
    nombre = categoria.nombre
    db.session.delete(categoria)
    db.session.commit()

    registrar_auditoria('delete', 'categoria_ingreso', id, {
        'nombre': nombre
    })

    flash(f'Categoría de ingreso "{nombre}" eliminada exitosamente.', 'success')
    return redirect(url_for('categorias.index'))


# ==================== CATEGORÍAS DE EGRESO ====================

@bp.route('/egreso/nueva', methods=['GET', 'POST'])
@login_required
@login_required_with_role('principal_organizacion', 'principal_sucursal')
def nueva_egreso():
    """
    Crear nueva categoría de egreso
    - Director organización: crea a nivel organización (compartida)
    - Gerente sucursal: crea a nivel sucursal (específica)
    """
    form = CategoriaForm()
    nivel = request.args.get('nivel', 'sucursal')  # organizacion o sucursal

    if form.validate_on_submit():
        # Determinar si es organizacional o de sucursal
        if current_user.es_principal_organizacion() and nivel == 'organizacion':
            # Verificar que no exista en la organización
            existe = CategoriaEgreso.query.filter_by(
                organizacion_id=current_user.organizacion_id,
                nombre=form.nombre.data
            ).first()

            if existe:
                flash(f'Ya existe una categoría organizacional de egreso con el nombre "{form.nombre.data}".', 'warning')
                return render_template('categorias/formulario.html', form=form, tipo='egreso', accion='nueva', nivel=nivel)

            # Crear categoría organizacional
            categoria = CategoriaEgreso(
                organizacion_id=current_user.organizacion_id,
                sucursal_id=None,
                nombre=form.nombre.data,
                descripcion=form.descripcion.data,
                activa=form.activa.data
            )

            nivel_texto = 'organización'
        else:
            # Crear categoría de sucursal
            existe = CategoriaEgreso.query.filter_by(
                sucursal_id=current_user.sucursal_id,
                nombre=form.nombre.data
            ).first()

            if existe:
                flash(f'Ya existe una categoría de sucursal de egreso con el nombre "{form.nombre.data}".', 'warning')
                return render_template('categorias/formulario.html', form=form, tipo='egreso', accion='nueva', nivel=nivel)

            categoria = CategoriaEgreso(
                organizacion_id=None,
                sucursal_id=current_user.sucursal_id,
                nombre=form.nombre.data,
                descripcion=form.descripcion.data,
                activa=form.activa.data
            )

            nivel_texto = 'sucursal'

        db.session.add(categoria)
        db.session.commit()

        registrar_auditoria('create', 'categoria_egreso', categoria.id, {
            'nombre': categoria.nombre,
            'nivel': nivel_texto,
            'organizacion_id': categoria.organizacion_id,
            'sucursal_id': categoria.sucursal_id
        })

        flash(f'Categoría de egreso "{categoria.nombre}" creada exitosamente a nivel {nivel_texto}.', 'success')
        return redirect(url_for('categorias.index'))

    return render_template('categorias/formulario.html', form=form, tipo='egreso', accion='nueva', nivel=nivel)


@bp.route('/egreso/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@login_required_with_role('principal_organizacion', 'principal_sucursal')
def editar_egreso(id):
    """
    Editar categoría de egreso
    """
    categoria = CategoriaEgreso.query.get_or_404(id)

    # Verificar permisos
    if categoria.organizacion_id:
        # Categoría organizacional - solo director de esa organización
        if not current_user.es_principal_organizacion() or categoria.organizacion_id != current_user.organizacion_id:
            flash('No tienes permiso para editar esta categoría organizacional.', 'danger')
            return redirect(url_for('categorias.index'))
        nivel = 'organizacion'
    else:
        # Categoría de sucursal - solo gerente de esa sucursal o director de la org
        if current_user.es_principal_organizacion():
            # Verificar que la sucursal pertenezca a su organización
            from app.models import Sucursal
            sucursal = Sucursal.query.get(categoria.sucursal_id)
            if not sucursal or sucursal.organizacion_id != current_user.organizacion_id:
                flash('No tienes permiso para editar esta categoría.', 'danger')
                return redirect(url_for('categorias.index'))
        elif categoria.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para editar esta categoría.', 'danger')
            return redirect(url_for('categorias.index'))
        nivel = 'sucursal'

    form = CategoriaForm(obj=categoria)

    if form.validate_on_submit():
        # Verificar que no exista otra categoría con el mismo nombre en el mismo nivel
        if nivel == 'organizacion':
            existe = CategoriaEgreso.query.filter(
                CategoriaEgreso.organizacion_id == categoria.organizacion_id,
                CategoriaEgreso.nombre == form.nombre.data,
                CategoriaEgreso.id != id
            ).first()
        else:
            existe = CategoriaEgreso.query.filter(
                CategoriaEgreso.sucursal_id == categoria.sucursal_id,
                CategoriaEgreso.nombre == form.nombre.data,
                CategoriaEgreso.id != id
            ).first()

        if existe:
            flash(f'Ya existe otra categoría de egreso con el nombre "{form.nombre.data}".', 'warning')
            return render_template('categorias/formulario.html', form=form, tipo='egreso', accion='editar', categoria=categoria, nivel=nivel)

        # Actualizar la categoría
        nombre_anterior = categoria.nombre
        categoria.nombre = form.nombre.data
        categoria.descripcion = form.descripcion.data
        categoria.activa = form.activa.data

        db.session.commit()

        registrar_auditoria('update', 'categoria_egreso', categoria.id, {
            'nombre_anterior': nombre_anterior,
            'nombre_nuevo': categoria.nombre
        })

        flash(f'Categoría de egreso "{categoria.nombre}" actualizada exitosamente.', 'success')
        return redirect(url_for('categorias.index'))

    return render_template('categorias/formulario.html', form=form, tipo='egreso', accion='editar', categoria=categoria, nivel=nivel)


@bp.route('/egreso/eliminar/<int:id>', methods=['POST'])
@login_required
@login_required_with_role('principal_organizacion', 'principal_sucursal')
def eliminar_egreso(id):
    """
    Eliminar categoría de egreso
    """
    categoria = CategoriaEgreso.query.get_or_404(id)

    # Verificar permisos
    if categoria.organizacion_id:
        if not current_user.es_principal_organizacion() or categoria.organizacion_id != current_user.organizacion_id:
            flash('No tienes permiso para eliminar esta categoría.', 'danger')
            return redirect(url_for('categorias.index'))
    else:
        if current_user.es_principal_organizacion():
            from app.models import Sucursal
            sucursal = Sucursal.query.get(categoria.sucursal_id)
            if not sucursal or sucursal.organizacion_id != current_user.organizacion_id:
                flash('No tienes permiso para eliminar esta categoría.', 'danger')
                return redirect(url_for('categorias.index'))
        elif categoria.sucursal_id != current_user.sucursal_id:
            flash('No tienes permiso para eliminar esta categoría.', 'danger')
            return redirect(url_for('categorias.index'))

    # Verificar si hay egresos asociados
    egresos_count = Egreso.query.filter_by(categoria_id=id).count()

    if egresos_count > 0:
        flash(f'No se puede eliminar la categoría "{categoria.nombre}" porque tiene {egresos_count} egreso(s) asociado(s). Puedes desactivarla en su lugar.', 'warning')
        return redirect(url_for('categorias.index'))

    # Eliminar la categoría
    nombre = categoria.nombre
    db.session.delete(categoria)
    db.session.commit()

    registrar_auditoria('delete', 'categoria_egreso', id, {
        'nombre': nombre
    })

    flash(f'Categoría de egreso "{nombre}" eliminada exitosamente.', 'success')
    return redirect(url_for('categorias.index'))
