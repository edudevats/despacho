from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            flash('Acceso denegado. Se requieren permisos de administrador.', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def inventory_admin_required(f):
    """Permite global admins o usuarios con perm_inventory_admin en la empresa."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        company_id = kwargs.get('company_id')
        if current_user.is_admin:
            return f(*args, **kwargs)
        if company_id is not None and current_user.is_inventory_admin_for(company_id):
            return f(*args, **kwargs)
        flash('Acceso denegado. Se requieren permisos de administrador de inventario.', 'error')
        return redirect(url_for('main.index'))
    return decorated_function

def require_company_perm(*perm_names):
    """Permite global admins o usuarios con AL MENOS UNO de los perms en la empresa
    identificada por kwargs['company_id']. Si no hay company_id, se exige que el
    usuario tenga el perm en ALGUNA empresa (caso rutas listadoras)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.is_admin:
                return f(*args, **kwargs)
            company_id = kwargs.get('company_id')
            if company_id is not None:
                if current_user.has_company_perm(company_id, *perm_names):
                    return f(*args, **kwargs)
            else:
                if current_user.has_any_perm(*perm_names):
                    return f(*args, **kwargs)
            flash('Acceso denegado. No tienes permiso para acceder a esta sección.', 'error')
            return redirect(url_for('main.index'))
        return decorated_function
    return decorator
