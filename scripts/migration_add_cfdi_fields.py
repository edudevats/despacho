
import sqlite3
import os

# Determinar la ruta a la base de datos (asumiendo que está en instance/sat.db basada en la estructura común de Flask)
# Ajustar según sea necesario si db.sqlite o similar se usa
DB_PATH = 'instance/sat_app.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    print(f"Migrating database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    columns_to_add = [
        ("periodicity", "VARCHAR(5)"),
        ("months", "VARCHAR(5)"),
        ("fiscal_year", "VARCHAR(5)"),
        ("payment_terms", "TEXT"),
        ("currency", "VARCHAR(5)"),
        ("exchange_rate", "FLOAT"),
        ("exportation", "VARCHAR(5)"),
        ("version", "VARCHAR(5)")
    ]

    for col_name, col_type in columns_to_add:
        try:
            print(f"Adding column {col_name}...")
            cursor.execute(f"ALTER TABLE invoice ADD COLUMN {col_name} {col_type}")
            print(f"Column {col_name} added successfully.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"Column {col_name} already exists. Skipping.")
            else:
                print(f"Error adding column {col_name}: {e}")

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
