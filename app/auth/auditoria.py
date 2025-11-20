"""
Sistema de Auditoría
Registra todas las acciones importantes en el sistema
"""
from app.models import Auditoria, db
from flask import request
from flask_login import current_user
import json


def registrar_auditoria(accion, tabla=None, registro_id=None, detalles=None):
    """
    Registra una acción en la auditoría

    Args:
        accion: Tipo de acción ('login', 'create', 'update', 'delete', 'export')
        tabla: Nombre de la tabla afectada ('ingreso', 'egreso', 'usuario', etc.)
        registro_id: ID del registro afectado
        detalles: Dict con detalles adicionales (se convertirá a JSON)

    Ejemplo:
        registrar_auditoria('create', 'ingreso', ingreso.id, {
            'monto': str(ingreso.monto),
            'categoria': ingreso.categoria.nombre
        })
    """
    try:
        auditoria = Auditoria(
            usuario_id=current_user.id if current_user.is_authenticated else None,
            clinica_id=(current_user.clinica_id
                       if current_user.is_authenticated and hasattr(current_user, 'clinica_id')
                       else None),
            accion=accion,
            tabla=tabla,
            registro_id=registro_id,
            detalles=json.dumps(detalles, ensure_ascii=False) if detalles else None,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None
        )

        db.session.add(auditoria)
        db.session.commit()

    except Exception as e:
        print(f"Error al registrar auditoría: {e}")
        db.session.rollback()


def registrar_login(usuario):
    """
    Registra un inicio de sesión exitoso

    Args:
        usuario: Objeto Usuario
    """
    registrar_auditoria(
        accion='login',
        detalles={
            'username': usuario.username,
            'rol': usuario.rol
        }
    )


def registrar_logout(usuario):
    """
    Registra un cierre de sesión

    Args:
        usuario: Objeto Usuario
    """
    registrar_auditoria(
        accion='logout',
        detalles={
            'username': usuario.username
        }
    )
