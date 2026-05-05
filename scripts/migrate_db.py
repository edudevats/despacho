"""
Migration script to add new columns to the invoice table.
Run this script once to update your existing database.
"""
import sqlite3
import os

# Path to the database
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'sat_app.db')

print(f"Database path: {db_path}")

if not os.path.exists(db_path):
    print("Database file not found. It will be created when you run the app.")
    exit(0)

# Connect to the database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# New columns to add
new_columns = [
    ('issuer_name', 'VARCHAR(256)'),
    ('receiver_name', 'VARCHAR(256)'),
    ('forma_pago', 'VARCHAR(3)'),
    ('metodo_pago', 'VARCHAR(3)'),
    ('uso_cfdi', 'VARCHAR(4)'),
    ('descripcion', 'TEXT'),
]

# Check existing columns
cursor.execute("PRAGMA table_info(invoice)")
existing_columns = [col[1] for col in cursor.fetchall()]
print(f"Existing columns: {existing_columns}")

# Add missing columns
for col_name, col_type in new_columns:
    if col_name not in existing_columns:
        try:
            cursor.execute(f"ALTER TABLE invoice ADD COLUMN {col_name} {col_type}")
            print(f"✓ Added column: {col_name}")
        except sqlite3.OperationalError as e:
            print(f"✗ Error adding {col_name}: {e}")
    else:
        print(f"- Column {col_name} already exists")

conn.commit()
conn.close()

print("\n✓ Migration completed successfully!")
