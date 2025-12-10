"""
Script de verificación completa de protecciones contra duplicados
"""
import sqlite3
import os

db_path = 'instance/sat_app.db'
facturas_dir = 'facturas'

print("=" * 80)
print("VERIFICACIÓN DE PROTECCIONES CONTRA DUPLICADOS")
print("=" * 80)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 1. Verificar constraint UNIQUE en invoice.uuid
print("\n1️⃣  PROTECCIÓN: invoice.uuid UNIQUE")
c.execute("PRAGMA table_info(invoice)")
columns = c.fetchall()
uuid_col = [col for col in columns if col[1] == 'uuid'][0]
print(f"   Columna uuid: {uuid_col}")

c.execute("PRAGMA index_list('invoice')")
indices = c.fetchall()
print(f"   Índices en invoice: {len(indices)}")

c.execute("""
    SELECT uuid, COUNT(*) as count 
    FROM invoice 
    GROUP BY uuid 
    HAVING COUNT(*) > 1
""")
duplicates = c.fetchall()

if duplicates:
    print(f"   ❌ DUPLICADOS ENCONTRADOS: {len(duplicates)}")
    for uuid, count in duplicates:
        print(f"      {uuid}: {count} veces")
else:
    print("   ✅ No hay UUIDs duplicados en la base de datos")

# 2. Verificar índice único en movement.invoice_id
print("\n2️⃣  PROTECCIÓN: movement.invoice_id UNIQUE INDEX")
c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_movement_invoice_unique'")
idx_exists = c.fetchone()

if idx_exists:
    print("   ✅ Índice único existe")
    
    c.execute("""
        SELECT invoice_id, COUNT(*) as count
        FROM movement
        GROUP BY invoice_id
        HAVING COUNT(*) > 1
    """)
    mov_duplicates = c.fetchall()
    
    if mov_duplicates:
        print(f"   ❌ DUPLICADOS: {len(mov_duplicates)} facturas con múltiples movimientos")
    else:
        print("   ✅ No hay movimientos duplicados")
else:
    print("   ⚠️  Índice único NO existe (ejecutar add_duplicate_protections.py)")

# 3. Verificar archivos XML duplicados
print("\n3️⃣  PROTECCIÓN: Archivos XML únicos")
if os.path.exists(facturas_dir):
    xml_files = {}
    for folder in os.listdir(facturas_dir):
        folder_path = os.path.join(facturas_dir, folder)
        if os.path.isdir(folder_path):
            for filename in os.listdir(folder_path):
                if filename.endswith('.xml'):
                    uuid = filename.replace('.xml', '')
                    if uuid in xml_files:
                        xml_files[uuid].append(folder)
                    else:
                        xml_files[uuid] = [folder]
    
    duplicated_xmls = {k: v for k, v in xml_files.items() if len(v) > 1}
    
    if duplicated_xmls:
        print(f"   ❌ DUPLICADOS: {len(duplicated_xmls)} XMLs en múltiples carpetas")
        for uuid, folders in list(duplicated_xmls.items())[:3]:
            print(f"      {uuid}: en {folders}")
    else:
        print(f"   ✅ {len(xml_files)} archivos XML únicos")

# 4. Verificar coherencia BD vs Archivos
print("\n4️⃣  COHERENCIA: Base de Datos vs Archivos")
c.execute("SELECT uuid FROM invoice")
db_uuids = {row[0] for row in c.fetchall()}
file_uuids = set(xml_files.keys()) if os.path.exists(facturas_dir) else set()

only_in_db = db_uuids - file_uuids
only_in_files = file_uuids - db_uuids

if only_in_db:
    print(f"   ⚠️  {len(only_in_db)} facturas solo en BD (sin XML)")
if only_in_files:
    print(f"   ⚠️  {len(only_in_files)} XMLs sin factura en BD")
if not only_in_db and not only_in_files:
    print(f"   ✅ {len(db_uuids)} facturas = {len(file_uuids)} XMLs")

# 5. Verificar que cada factura tenga máximo un movimiento
print("\n5️⃣  INTEGRIDAD: Factura-Movimiento (1:1)")
c.execute("""
    SELECT 
        COUNT(DISTINCT i.id) as total_invoices,
        COUNT(DISTINCT m.invoice_id) as invoices_with_movement,
        COUNT(m.id) as total_movements
    FROM invoice i
    LEFT JOIN movement m ON m.invoice_id = i.id
""")
total_inv, inv_with_mov, total_mov = c.fetchone()

print(f"   Facturas totales: {total_inv}")
print(f"   Facturas con movimiento: {inv_with_mov}")
print(f"   Movimientos totales: {total_mov}")

if total_inv == inv_with_mov == total_mov:
    print("   ✅ Relación 1:1 perfecta")
elif total_inv == total_mov:
    print("   ✅ Cada factura tiene exactamente un movimiento")
else:
    print(f"   ⚠️  Inconsistencia detectada")

conn.close()

print("\n" + "=" * 80)
print("RESUMEN DE PROTECCIONES:")
print("=" * 80)
print("✅ = Protección activa y funcionando")
print("⚠️  = Requiere atención")
print("❌ = Problema detectado")
print("=" * 80)
