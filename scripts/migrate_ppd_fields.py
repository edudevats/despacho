"""
Script para agregar campos de acreditación PPD al modelo Invoice.
Ejecutar: python scripts/migrate_ppd_fields.py
"""
import sqlite3
import os

def migrate():
    # Determinar la ruta de la base de datos
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'sat_app.db')
    
    if not os.path.exists(db_path):
        print(f"No se encontró la base de datos en: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Nuevas columnas a agregar
    new_columns = [
        ('ppd_acreditado', 'BOOLEAN DEFAULT 0'),
        ('ppd_fecha_acreditacion', 'DATETIME'),
        ('ppd_mes_acreditado', 'INTEGER'),
        ('ppd_anio_acreditado', 'INTEGER'),
    ]
    
    # Verificar y agregar cada columna
    for col_name, col_type in new_columns:
        try:
            # Verificar si la columna ya existe
            cursor.execute(f"SELECT {col_name} FROM invoice LIMIT 1")
            print(f"Columna '{col_name}' ya existe")
        except sqlite3.OperationalError:
            # La columna no existe, agregarla
            try:
                cursor.execute(f"ALTER TABLE invoice ADD COLUMN {col_name} {col_type}")
                print(f"Columna '{col_name}' agregada exitosamente")
            except Exception as e:
                print(f"Error agregando columna '{col_name}': {e}")
    
    conn.commit()
    conn.close()
    print("\nMigración completada.")

if __name__ == '__main__':
    migrate()
