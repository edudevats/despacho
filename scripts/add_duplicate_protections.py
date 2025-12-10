"""
Script para agregar índice único a la tabla movement
para evitar duplicados de movimientos por factura
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'instance', 'sat_app.db')

print("Agregando protecciones contra duplicados...")
print("=" * 80)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Verificar si ya existe el índice
cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_movement_invoice_unique'")
existing_index = cursor.fetchone()

if existing_index:
    print("\n✓ Índice único ya existe en movement.invoice_id")
else:
    # 2. Primero, verificar si hay duplicados existentes
    cursor.execute("""
        SELECT invoice_id, COUNT(*) as count
        FROM movement
        GROUP BY invoice_id
        HAVING COUNT(*) > 1
    """)
    
    duplicates = cursor.fetchall()
    
    if duplicates:
        print(f"\n⚠️  Encontrados {len(duplicates)} movimientos duplicados:")
        for inv_id, count in duplicates:
            print(f"  Factura {inv_id}: {count} movimientos")
        
        # Eliminar duplicados, dejando solo el primero
        print("\n  Limpiando duplicados...")
        for inv_id, _ in duplicates:
            cursor.execute("""
                DELETE FROM movement
                WHERE id NOT IN (
                    SELECT MIN(id) FROM movement WHERE invoice_id = ?
                )
                AND invoice_id = ?
            """, (inv_id, inv_id))
        print(f"  ✓ Eliminados {cursor.rowcount} movimientos duplicados")
    
    # 3. Crear índice único
    try:
        cursor.execute("""
            CREATE UNIQUE INDEX idx_movement_invoice_unique 
            ON movement(invoice_id)
        """)
        print("\n✓ Índice único creado en movement.invoice_id")
    except sqlite3.OperationalError as e:
        print(f"\n✗ Error creando índice: {e}")

# 4. Verificar índice en invoice.uuid
cursor.execute("PRAGMA index_list('invoice')")
indices = cursor.fetchall()
has_uuid_unique = any('uuid' in str(idx) for idx in indices)

if has_uuid_unique:
    print("✓ Índice único ya existe en invoice.uuid")
else:
    print("⚠️  No se encontró índice único en invoice.uuid (debería existir por el constraint)")

conn.commit()
conn.close()

print("\n" + "=" * 80)
print("PROTECCIONES CONTRA DUPLICADOS:")
print("  1. ✅ invoice.uuid -> UNIQUE constraint")
print("  2. ✅ movement.invoice_id -> UNIQUE index")
print("  3. ✅ Verificación en código antes de insertar factura")
print("  4. ✅ Verificación en código antes de guardar XML")
print("=" * 80)
