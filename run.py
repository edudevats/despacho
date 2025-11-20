"""
Punto de entrada del Sistema de Contaduría Multiclinicas
"""
import os
from app import create_app, db
from app.models import (
    Usuario, Organizacion, Sucursal, Ingreso, Egreso,
    CategoriaIngreso, CategoriaEgreso, Auditoria,
    Proveedor, FacturaCFDI
)

# Crear aplicación
app = create_app(os.getenv('FLASK_ENV') or 'development')


@app.shell_context_processor
def make_shell_context():
    """
    Hace que estos objetos estén disponibles automáticamente
    en el shell de Flask (flask shell)
    """
    return {
        'db': db,
        'Usuario': Usuario,
        'Organizacion': Organizacion,
        'Sucursal': Sucursal,
        'Ingreso': Ingreso,
        'Egreso': Egreso,
        'CategoriaIngreso': CategoriaIngreso,
        'CategoriaEgreso': CategoriaEgreso,
        'Auditoria': Auditoria,
        'Proveedor': Proveedor,
        'FacturaCFDI': FacturaCFDI
    }


@app.cli.command()
def init_db():
    """Inicializa la base de datos"""
    db.create_all()
    print('✓ Base de datos inicializada')


@app.cli.command()
def seed_db():
    """Carga datos de demostración"""
    from seed_data import seed_database
    seed_database()
    print('✓ Datos de demostración cargados')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
