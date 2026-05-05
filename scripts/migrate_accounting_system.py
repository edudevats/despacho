"""
Migración para agregar tablas Category y Supplier, y actualizar Movement e Invoice
"""
import sqlite3
import os
from datetime import datetime

db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'sat_app.db')

print("=" * 80)
print("MIGRACIÓN: Sistema de Contaduría Completo")
print("=" * 80)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Crear tabla Category
print("\n1. Creando tabla 'category'...")
try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS category (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(10) NOT NULL,
            description TEXT,
            is_default BOOLEAN DEFAULT 0,
            active BOOLEAN DEFAULT 1,
            color VARCHAR(7) DEFAULT '#6c757d',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES company(id)
        )
    """)
    print("   ✓ Tabla 'category' creada")
except sqlite3.OperationalError as e:
    print(f"   ⚠ Tabla 'category' ya existe o error: {e}")

# 2. Crear tabla Supplier
print("\n2. Creando tabla 'supplier'...")
try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supplier (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            rfc VARCHAR(13) NOT NULL,
            business_name VARCHAR(256),
            commercial_name VARCHAR(256),
            email VARCHAR(120),
            phone VARCHAR(20),
            address TEXT,
            total_invoiced REAL DEFAULT 0,
            invoice_count INTEGER DEFAULT 0,
            last_invoice_date TIMESTAMP,
            first_invoice_date TIMESTAMP,
            notes TEXT,
            tags VARCHAR(256),
            is_favorite BOOLEAN DEFAULT 0,
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES company(id),
            UNIQUE(company_id, rfc)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier_rfc ON supplier(rfc)")
    print("   ✓ Tabla 'supplier' creada")
except sqlite3.OperationalError as e:
    print(f"   ⚠ Tabla 'supplier' ya existe o error: {e}")

# 3. Agregar columnas a Invoice
print("\n3. Actualizando tabla 'invoice'...")
new_invoice_columns = [
    ('supplier_id', 'INTEGER'),
]

cursor.execute("PRAGMA table_info(invoice)")
existing_cols = [col[1] for col in cursor.fetchall()]

for col_name, col_type in new_invoice_columns:
    if col_name not in existing_cols:
        try:
            cursor.execute(f"ALTER TABLE invoice ADD COLUMN {col_name} {col_type}")
            print(f"   ✓ Columna '{col_name}' agregada a invoice")
        except sqlite3.OperationalError as e:
            print(f"   ✗ Error agregando {col_name}: {e}")
    else:
        print(f"   - Columna '{col_name}' ya existe")

# Crear foreign key si no existe (SQLite no soporta ADD CONSTRAINT, ya está en CREATE)
try:
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoice_supplier ON invoice(supplier_id)")
    print("   ✓ Índice de supplier_id creado")
except:
    pass

# 4. Agregar columnas a Movement
print("\n4. Actualizando tabla 'movement'...")
new_movement_columns = [
    ('category_id', 'INTEGER'),
    ('source', 'VARCHAR(20) DEFAULT \'invoice\''),
    ('notes', 'TEXT'),
]

cursor.execute("PRAGMA table_info(movement)")
existing_cols = [col[1] for col in cursor.fetchall()]

for col_name, col_type in new_movement_columns:
    if col_name not in existing_cols:
        try:
            cursor.execute(f"ALTER TABLE movement ADD COLUMN {col_name} {col_type}")
            print(f"   ✓ Columna '{col_name}' agregada a movement")
        except sqlite3.OperationalError as e:
            print(f"   ✗ Error agregando {col_name}: {e}")
    else:
        print(f"   - Columna '{col_name}' ya existe")

try:
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movement_category ON movement(category_id)")
    print("   ✓ Índice de category_id creado")
except:
    pass

conn.commit()

# 5. Crear categorías por defecto
print("\n5. Creando categorías por defecto...")

# Obtener todas las empresas
cursor.execute("SELECT id, name FROM company")
companies = cursor.fetchall()

default_categories_income = [
    ('Ventas de Productos', '#28a745'),
    ('Servicios Profesionales', '#17a2b8'),
    ('Otros Ingresos', '#6c757d'),
]

default_categories_expense = [
    ('Nómina y Sueldos', '#dc3545'),
    ('Renta y Servicios', '#fd7e14'),
    ('Compras e Insumos', '#ffc107'),
    ('Servicios Profesionales', '#6f42c1'),
    ('Impuestos y Cuotas', '#e83e8c'),
    ('Publicidad y Marketing', '#20c997'),
    ('Gastos Administrativos', '#6c757d'),
    ('Otros Gastos', '#343a40'),
]

for company_id, company_name in companies:
    print(f"\n   Empresa: {company_name}")
    
    # Categorías de ingreso
    for cat_name, color in default_categories_income:
        cursor.execute("""
            SELECT id FROM category 
            WHERE company_id = ? AND name = ? AND type = 'INCOME'
        """, (company_id, cat_name))
        
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO category (company_id, name, type, color, is_default, active)
                VALUES (?, ?, 'INCOME', ?, 1, 1)
            """, (company_id, cat_name, color))
            print(f"      ✓ {cat_name} (INCOME)")
    
    # Categorías de egreso
    for cat_name, color in default_categories_expense:
        cursor.execute("""
            SELECT id FROM category 
            WHERE company_id = ? AND name = ? AND type = 'EXPENSE'
        """, (company_id, cat_name))
        
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO category (company_id, name, type, color, is_default, active)
                VALUES (?, ?, 'EXPENSE', ?, 1, 1)
            """, (company_id, cat_name, color))
            print(f"      ✓ {cat_name} (EXPENSE)")

conn.commit()

# 6. Generar proveedores desde facturas existentes
print("\n6. Generando proveedores desde facturas recibidas...")

cursor.execute("SELECT id, name, rfc FROM company")
companies = cursor.fetchall()

total_suppliers = 0
for company_id, company_name, company_rfc in companies:
    print(f"\n   Empresa: {company_name}")
    
    # Facturas donde esta empresa es el receptor (facturas recibidas)
    cursor.execute("""
        SELECT DISTINCT issuer_rfc, issuer_name, 
               MIN(date) as first_date,
               MAX(date) as last_date,
               COUNT(*) as count,
               SUM(total) as total
        FROM invoice
        WHERE company_id = ? AND receiver_rfc = ? AND issuer_rfc IS NOT NULL
        GROUP BY issuer_rfc
    """, (company_id, company_rfc))
    
    suppliers_data = cursor.fetchall()
    
    for issuer_rfc, issuer_name, first_date, last_date, inv_count, total in suppliers_data:
        # Verificar si el proveedor ya existe
        cursor.execute("""
            SELECT id FROM supplier WHERE company_id = ? AND rfc = ?
        """, (company_id, issuer_rfc))
        
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO supplier (
                    company_id, rfc, business_name, 
                    first_invoice_date, last_invoice_date,
                    invoice_count, total_invoiced, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (company_id, issuer_rfc, issuer_name, first_date, last_date, inv_count, total))
            
            supplier_id = cursor.lastrowid
            
            # Actualizar facturas con el supplier_id
            cursor.execute("""
                UPDATE invoice SET supplier_id = ?
                WHERE company_id = ? AND issuer_rfc = ?
            """, (supplier_id, company_id, issuer_rfc))
            
            print(f"      ✓ {issuer_name} ({issuer_rfc}) - {inv_count} facturas, ${total:,.2f}")
            total_suppliers += 1

conn.commit()
conn.close()

print("\n" + "=" * 80)
print(f"✓ MIGRACIÓN COMPLETADA")
print(f"  - Tablas creadas: category, supplier")
print(f"  - Columnas agregadas a invoice y movement")
print(f"  - Categorías por defecto creadas")
print(f"  - {total_suppliers} proveedores generados automáticamente")
print("=" * 80)
