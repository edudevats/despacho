"""
Script para crear movimientos (INCOME/EXPENSE) para todas las facturas
que no tienen movimiento asociado.
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'instance', 'sat_app.db')

def create_movements():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Obtener facturas sin movimiento
    cursor.execute("""
        SELECT i.id, i.company_id, i.type, i.total, i.date,
               i.issuer_rfc, i.receiver_rfc, c.rfc
        FROM invoice i
        JOIN company c ON i.company_id = c.id
        LEFT JOIN movement m ON m.invoice_id = i.id
        WHERE m.id IS NULL
    """)
    
    invoices_without_movement = cursor.fetchall()
    
    print(f"Facturas sin movimiento: {len(invoices_without_movement)}")
    print("=" * 80)
    
    created = 0
    for inv_id, company_id, inv_type, total, date, issuer_rfc, receiver_rfc, company_rfc in invoices_without_movement:
        # Extract just the code if it contains full text like "I - Ingreso"
        if inv_type and ' - ' in inv_type:
            inv_type = inv_type.split(' - ')[0]
        
        # Determinar si es emitida o recibida
        is_emitted = (issuer_rfc == company_rfc)
        
        # Lógica de movimiento
        mov_type = None
        if is_emitted:
            if inv_type == 'I':
                mov_type = 'INCOME'  # Venta
            elif inv_type == 'E':
                mov_type = 'EXPENSE'  # Nota de crédito
        else:  # Received
            if inv_type == 'I':
                mov_type = 'EXPENSE'  # Compra
            elif inv_type == 'E':
                mov_type = 'INCOME'  # Devolución recibida
        
        if mov_type:
            other_party = receiver_rfc if is_emitted else issuer_rfc
            description = f"Factura {other_party} ({inv_type})"
            
            cursor.execute("""
                INSERT INTO movement (invoice_id, company_id, amount, type, description, date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (inv_id, company_id, total, mov_type, description, date))
            
            tipo_factura = "EMITIDA" if is_emitted else "RECIBIDA"
            print(f"  ✓ {tipo_factura:9} | {mov_type:8} | ${total:>10,.2f}")
            created += 1
        else:
            print(f"  ⚠ No se pudo determinar tipo de movimiento para factura {inv_id} (tipo: {inv_type})")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 80)
    print(f"✓ Movimientos creados: {created}")
    
    # Resumen final
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT type, COUNT(*), SUM(amount)
        FROM movement
        GROUP BY type
    """)
    
    print("\nRESUMEN DE MOVIMIENTOS:")
    print("-" * 80)
    for row in cursor.fetchall():
        print(f"  {row[0]:10} | {row[1]:3} movimientos | ${row[2]:>12,.2f}")
    
    conn.close()

if __name__ == "__main__":
    create_movements()
