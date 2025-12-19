import sqlite3
import os

# Ruta a la base de datos
db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'sat_app.db')

print(f"Conectando a base de datos: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Agregar columna logo_path
    cursor.execute("ALTER TABLE company ADD COLUMN logo_path VARCHAR(512)")
    conn.commit()
    print("✓ Columna logo_path agregada exitosamente a la tabla company")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("✓ Columna logo_path ya existe en la tabla company")
    else:
        print(f"✗ Error: {e}")
        raise
finally:
    conn.close()

print("Migración completada")
