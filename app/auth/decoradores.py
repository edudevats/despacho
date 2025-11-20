"""
Decoradores de permisos para control de acceso
Sistema de jerarquía de 4 niveles: Despacho -> Organizaciones -> Sucursales -> POS
"""
from functools import wraps
from flask import abort, redirect, url_for, flash, request
from flask_login import current_user


def login_required_with_role(*roles):
    """
    Requiere login y verifica que el usuario tenga uno de los roles especificados

    Uso:
        @login_required_with_role('admin_despacho', 'principal_organizacion', 'principal_sucursal')
        def mi_vista():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            if current_user.rol not in roles:
                flash('No tienes permisos para acceder a esta página.', 'danger')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_despacho_required(f):
    """
    Solo administradores del despacho pueden acceder
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if not current_user.es_admin_despacho():
            flash('Acceso denegado. Solo administradores del despacho.', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def principal_organizacion_required(f):
    """
    Solo directores de organización pueden acceder
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if not current_user.es_principal_organizacion():
            flash('Acceso denegado. Solo directores de organización.', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def principal_sucursal_required(f):
    """
    Solo gerentes de sucursal pueden acceder
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if not current_user.es_principal_sucursal():
            flash('Acceso denegado. Solo gerentes de sucursal.', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


# Decorador legacy mantenido para compatibilidad
def principal_clinica_required(f):
    """
    DEPRECADO: Usar principal_sucursal_required en su lugar
    Solo usuarios principales de sucursal pueden acceder
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if not current_user.es_principal_sucursal():
            flash('Acceso denegado. Solo usuarios principales de sucursal.', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def misma_organizacion_required(f):
    """
    Verifica que el usuario acceda solo a datos de su organización
    - Admin del despacho puede ver todo
    - Directores de organización solo ven su organización
    - Gerentes de sucursal y POS solo ven su organización
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # El admin del despacho puede ver todo
        if current_user.es_admin_despacho():
            return f(*args, **kwargs)

        # Obtener organizacion_id del request (kwargs, query params o form)
        organizacion_id = (kwargs.get('organizacion_id') or
                          request.args.get('organizacion_id') or
                          request.form.get('organizacion_id'))

        if organizacion_id and int(organizacion_id) != current_user.organizacion_id:
            flash('No puedes acceder a datos de otra organización.', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def misma_sucursal_required(f):
    """
    Verifica que el usuario acceda solo a datos de su sucursal
    - Admin del despacho puede ver todo
    - Directores de organización pueden ver todas las sucursales de su organización
    - Gerentes de sucursal solo ven su sucursal
    - Usuarios POS solo ven su sucursal
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # El admin del despacho puede ver todo
        if current_user.es_admin_despacho():
            return f(*args, **kwargs)

        # Obtener sucursal_id del request (kwargs, query params o form)
        sucursal_id = (kwargs.get('sucursal_id') or
                      kwargs.get('id') or  # Para rutas como /sucursales/<int:id>
                      request.args.get('sucursal_id') or
                      request.form.get('sucursal_id'))

        if sucursal_id:
            sucursal_id = int(sucursal_id)

            # Directores de organización pueden ver todas sus sucursales
            if current_user.es_principal_organizacion():
                from app.models import Sucursal
                sucursal = Sucursal.query.get_or_404(sucursal_id)
                if sucursal.organizacion_id != current_user.organizacion_id:
                    flash('No puedes acceder a datos de otra organización.', 'danger')
                    abort(403)
                return f(*args, **kwargs)

            # Gerentes de sucursal y POS solo ven su propia sucursal
            if sucursal_id != current_user.sucursal_id:
                flash('No puedes acceder a datos de otra sucursal.', 'danger')
                abort(403)

        return f(*args, **kwargs)
    return decorated_function


# Decorador legacy mantenido para compatibilidad (apunta a misma_sucursal_required)
def misma_clinica_required(f):
    """
    DEPRECADO: Usar misma_sucursal_required en su lugar
    Verifica que el usuario acceda solo a datos de su sucursal
    """
    return misma_sucursal_required(f)


def permiso_registrar_ingresos_required(f):
    """
    Verifica permiso para registrar ingresos
    - Admins del despacho NO pueden (solo lectura)
    - Directores de organización SÍ pueden
    - Gerentes de sucursal SÍ pueden
    - Usuarios POS solo si tienen el permiso
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # Admin del despacho NO puede registrar (solo lectura)
        if current_user.es_admin_despacho():
            flash('Los administradores del despacho solo tienen acceso de lectura.', 'warning')
            abort(403)

        # Directores de organización y gerentes de sucursal siempre pueden
        if current_user.es_principal_organizacion() or current_user.es_principal_sucursal():
            return f(*args, **kwargs)

        # Usuarios POS solo si tienen el permiso
        if current_user.es_secundario_pos() and not current_user.puede_registrar_ingresos:
            flash('No tienes permiso para registrar ingresos.', 'warning')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def permiso_registrar_egresos_required(f):
    """
    Verifica permiso para registrar egresos
    - Admins del despacho NO pueden (solo lectura)
    - Directores de organización SÍ pueden
    - Gerentes de sucursal SÍ pueden
    - Usuarios POS solo si tienen el permiso
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # Admin del despacho NO puede registrar (solo lectura)
        if current_user.es_admin_despacho():
            flash('Los administradores del despacho solo tienen acceso de lectura.', 'warning')
            abort(403)

        # Directores de organización y gerentes de sucursal siempre pueden
        if current_user.es_principal_organizacion() or current_user.es_principal_sucursal():
            return f(*args, **kwargs)

        # Usuarios POS solo si tienen el permiso
        if current_user.es_secundario_pos() and not current_user.puede_registrar_egresos:
            flash('No tienes permiso para registrar egresos.', 'warning')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def permiso_editar_movimientos_required(f):
    """
    Verifica permiso para editar movimientos existentes
    - Admins del despacho NO pueden (solo lectura)
    - Directores de organización SÍ pueden
    - Gerentes de sucursal SÍ pueden
    - Usuarios POS solo si tienen el permiso
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # Admin del despacho NO puede editar (solo lectura)
        if current_user.es_admin_despacho():
            flash('Los administradores del despacho solo tienen acceso de lectura.', 'warning')
            abort(403)

        # Directores de organización y gerentes de sucursal siempre pueden
        if current_user.es_principal_organizacion() or current_user.es_principal_sucursal():
            return f(*args, **kwargs)

        # Usuarios POS solo si tienen el permiso
        if current_user.es_secundario_pos() and not current_user.puede_editar_movimientos:
            flash('No tienes permiso para editar movimientos.', 'warning')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def permiso_eliminar_movimientos_required(f):
    """
    Verifica permiso para eliminar movimientos
    - Admins del despacho NO pueden (solo lectura)
    - Directores de organización SÍ pueden
    - Gerentes de sucursal SÍ pueden
    - Usuarios POS solo si tienen el permiso
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # Admin del despacho NO puede eliminar (solo lectura)
        if current_user.es_admin_despacho():
            flash('Los administradores del despacho solo tienen acceso de lectura.', 'warning')
            abort(403)

        # Directores de organización y gerentes de sucursal siempre pueden
        if current_user.es_principal_organizacion() or current_user.es_principal_sucursal():
            return f(*args, **kwargs)

        # Usuarios POS solo si tienen el permiso
        if current_user.es_secundario_pos() and not current_user.puede_eliminar_movimientos:
            flash('No tienes permiso para eliminar movimientos.', 'warning')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def permiso_ver_reportes_required(f):
    """
    Verifica permiso para ver reportes
    - Admins del despacho SÍ pueden (lectura global)
    - Directores de organización SÍ pueden
    - Gerentes de sucursal SÍ pueden
    - Usuarios POS solo si tienen el permiso
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # Admins, directores y gerentes siempre pueden
        if (current_user.es_admin_despacho() or
            current_user.es_principal_organizacion() or
            current_user.es_principal_sucursal()):
            return f(*args, **kwargs)

        # Usuarios POS solo si tienen el permiso
        if current_user.es_secundario_pos() and not current_user.puede_ver_reportes:
            flash('No tienes permiso para ver reportes.', 'warning')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function
