"""
Script para limpiar los valores de los campos Code en la base de datos,
extrayendo solo el código corto de valores como "I - Ingreso" -> "I"
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'instance', 'sat_app.db')

def clean_code_fields():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Limpiando campos Code en la base de datos...")
    print("=" * 80)
    
    # Limpiar campo type
    cursor.execute("SELECT id, type FROM invoice WHERE type LIKE '% - %'")
    invoices_to_clean = cursor.fetchall()
    
    print(f"\nFacturas con tipo largo: {len(invoices_to_clean)}")
    for inv_id, inv_type in invoices_to_clean:
        short_type = inv_type.split(' - ')[0] if ' - ' in inv_type else inv_type
        cursor.execute("UPDATE invoice SET type = ? WHERE id = ?", (short_type, inv_id))
        print(f"  {inv_type:20} -> {short_type}")
    
    # Limpiar forma_pago
    cursor.execute("SELECT id, forma_pago FROM invoice WHERE forma_pago LIKE '% - %'")
    formas_to_clean = cursor.fetchall()
    
    if formas_to_clean:
        print(f"\nFormas de pago con texto largo: {len(formas_to_clean)}")
        for inv_id, forma in formas_to_clean:
            short_forma = forma.split(' - ')[0] if ' - ' in forma else forma
            cursor.execute("UPDATE invoice SET forma_pago = ? WHERE id = ?", (short_forma, inv_id))
            print(f"  {forma[:40]:40} -> {short_forma}")
    
    # Limpiar metodo_pago
    cursor.execute("SELECT id, metodo_pago FROM invoice WHERE metodo_pago LIKE '% - %'")
    metodos_to_clean = cursor.fetchall()
    
    if metodos_to_clean:
        print(f"\nMétodos de pago con texto largo: {len(metodos_to_clean)}")
        for inv_id, metodo in metodos_to_clean:
            short_metodo = metodo.split(' - ')[0] if ' - ' in metodo else metodo
            cursor.execute("UPDATE invoice SET metodo_pago = ? WHERE id = ?", (short_metodo, inv_id))
            print(f"  {metodo[:40]:40} -> {short_metodo}")
    
    # Limpiar uso_cfdi
    cursor.execute("SELECT id, uso_cfdi FROM invoice WHERE uso_cfdi LIKE '% - %'")
    usos_to_clean = cursor.fetchall()
    
    if usos_to_clean:
        print(f"\nUsos CFDI con texto largo: {len(usos_to_clean)}")
        for inv_id, uso in usos_to_clean:
            short_uso = uso.split(' - ')[0] if ' - ' in uso else uso
            cursor.execute("UPDATE invoice SET uso_cfdi = ? WHERE id = ?", (short_uso, inv_id))
            print(f"  {uso[:40]:40} -> {short_uso}")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✓ Limpieza completada")
    
    # Verificar resultado
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT type FROM invoice WHERE type IS NOT NULL")
    types = [r[0] for r in cursor.fetchall()]
    print(f"\nTipos de comprobante ahora: {', '.join(types)}")
    
    cursor.execute("SELECT DISTINCT forma_pago FROM invoice WHERE forma_pago IS NOT NULL LIMIT 5")
    formas = [r[0] for r in cursor.fetchall()]
    print(f"Formas de pago (ejemplos): {', '.join(formas)}")
    
    conn.close()

if __name__ == "__main__":
    clean_code_fields()
