"""
Script para cargar todas las facturas desde la carpeta facturas/ a la base de datos.
Distingue correctamente entre facturas EMITIDAS y RECIBIDAS.
"""
import sqlite3
import os
from satcfdi.cfdi import CFDI
from datetime import datetime

# Rutas
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'sat_app.db')
facturas_dir = os.path.join(os.path.dirname(__file__), 'facturas')

def extract_code_value(code_obj):
    """Extrae el valor de un objeto Code de satcfdi"""
    if code_obj is None:
        return None
    # Code objects have a .code attribute with just the code value
    if hasattr(code_obj, 'code'):
        return code_obj.code
    # Fallback to string conversion
    return str(code_obj)

def parse_invoice_from_xml(xml_path):
    """Parsea un XML de factura y extrae todos los campos"""
    try:
        with open(xml_path, 'rb') as f:
            xml_content = f.read()
            cfdi = CFDI.from_string(xml_content)
        
        # UUID
        uuid = cfdi.get('Complemento', {}).get('TimbreFiscalDigital', {}).get('UUID')
        if not uuid:
            return None
        
        # Montos
        total = float(cfdi.get('Total', 0))
        subtotal = float(cfdi.get('SubTotal', 0))
        tax = total - subtotal
        
        # Fecha
        fecha_obj = cfdi['Fecha']
        if isinstance(fecha_obj, str):
            if 'T' in fecha_obj:
                date = datetime.fromisoformat(fecha_obj.replace('Z', '+00:00'))
            else:
                date = datetime.strptime(fecha_obj, '%Y-%m-%d')
        else:
            date = fecha_obj
        
        # Tipo de comprobante
        tipo_comprobante = cfdi.get('TipoDeComprobante')
        tipo_str = extract_code_value(tipo_comprobante)
        
        # Emisor y Receptor
        emisor = cfdi.get('Emisor', {})
        receptor = cfdi.get('Receptor', {})
        
        issuer_rfc = emisor.get('Rfc')
        issuer_name = emisor.get('Nombre')
        receiver_rfc = receptor.get('Rfc')
        receiver_name = receptor.get('Nombre')
        
        # Forma y método de pago
        forma_pago = extract_code_value(cfdi.get('FormaPago'))
        metodo_pago = extract_code_value(cfdi.get('MetodoPago'))
        uso_cfdi = extract_code_value(receptor.get('UsoCFDI'))
        
        # Descripción del primer concepto
        descripcion = None
        try:
            conceptos = cfdi.get('Conceptos', [])
            if conceptos:
                if isinstance(conceptos, list) and len(conceptos) > 0:
                    concepto = conceptos[0]
                    descripcion = concepto.get('Descripcion', '') if isinstance(concepto, dict) else None
                elif isinstance(conceptos, dict):
                    concepto = conceptos.get('Concepto', [])
                    if isinstance(concepto, list) and len(concepto) > 0:
                        descripcion = concepto[0].get('Descripcion', '')
                    elif isinstance(concepto, dict):
                        descripcion = concepto.get('Descripcion', '')
        except:
            pass
        
        return {
            'uuid': uuid,
            'date': date,
            'total': total,
            'subtotal': subtotal,
            'tax': tax,
            'type': tipo_str,
            'issuer_rfc': issuer_rfc,
            'issuer_name': issuer_name,
            'receiver_rfc': receiver_rfc,
            'receiver_name': receiver_name,
            'forma_pago': forma_pago,
            'metodo_pago': metodo_pago,
            'uso_cfdi': uso_cfdi,
            'descripcion': descripcion,
            'xml': xml_content.decode('utf-8')
        }
    except Exception as e:
        print(f"  ✗ Error parseando {os.path.basename(xml_path)}: {e}")
        return None

def load_invoices():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Buscar carpeta de facturas
    company_folder = None
    for folder in os.listdir(facturas_dir):
        folder_path = os.path.join(facturas_dir, folder)
        if os.path.isdir(folder_path):
            company_folder = folder_path
            break
    
    if not company_folder:
        print("✗ No se encontró carpeta de facturas")
        conn.close()
        return
    
    print(f"Carpeta: {os.path.basename(company_folder)}\n")
    
    # Leer primer XML para identificar la empresa
    xml_files = [f for f in os.listdir(company_folder) if f.endswith('.xml')]
    if not xml_files:
        print("✗ No hay archivos XML en la carpeta")
        conn.close()
        return
    
    # Parsear primer XML para identificar RFCs
    first_xml = os.path.join(company_folder, xml_files[0])
    test_inv = parse_invoice_from_xml(first_xml)
    if not test_inv:
        print("✗ No se pudo parsear el primer XML")
        conn.close()
        return
    
    # Buscar empresa que coincida con emisor o receptor
    cursor.execute("SELECT id, rfc, name FROM company WHERE rfc = ? OR rfc = ?", 
                   (test_inv['issuer_rfc'], test_inv['receiver_rfc']))
    company = cursor.fetchone()
    
    if not company:
        print(f"✗ No se encontró empresa con RFC {test_inv['issuer_rfc']} o {test_inv['receiver_rfc']}")
        print("  Empresas disponibles:")
        cursor.execute("SELECT id, rfc, name FROM company")
        for c in cursor.fetchall():
            print(f"    {c[1]} - {c[2]}")
        conn.close()
        return
    
    company_id, company_rfc, company_name = company
    print(f"Empresa: {company_name} (RFC: {company_rfc})")
    print("="*80)
    print(f"Facturas encontradas en carpeta: {len(xml_files)}\n")
    
    added = 0
    updated = 0
    emitidas = 0
    recibidas = 0
    
    for xml_file in xml_files:
        xml_path = os.path.join(company_folder, xml_file)
        inv_data = parse_invoice_from_xml(xml_path)
        
        if not inv_data:
            continue
        
        # Determinar si es emitida o recibida
        is_emitted = (inv_data['issuer_rfc'] == company_rfc)
        tipo_factura = "EMITIDA" if is_emitted else "RECIBIDA"
        
        if is_emitted:
            emitidas += 1
        else:
            recibidas += 1
        
        # Verificar si ya existe
        cursor.execute("SELECT id FROM invoice WHERE uuid = ?", (inv_data['uuid'],))
        existing = cursor.fetchone()
        
        if existing:
            # Actualizar
            cursor.execute("""
                UPDATE invoice 
                SET date = ?, total = ?, subtotal = ?, tax = ?, type = ?,
                    issuer_rfc = ?, issuer_name = ?, receiver_rfc = ?, receiver_name = ?,
                    forma_pago = ?, metodo_pago = ?, uso_cfdi = ?, descripcion = ?,
                    xml_content = ?
                WHERE uuid = ?
            """, (
                inv_data['date'], inv_data['total'], inv_data['subtotal'], 
                inv_data['tax'], inv_data['type'],
                inv_data['issuer_rfc'], inv_data['issuer_name'],
                inv_data['receiver_rfc'], inv_data['receiver_name'],
                inv_data['forma_pago'], inv_data['metodo_pago'],
                inv_data['uso_cfdi'], inv_data['descripcion'],
                inv_data['xml'], inv_data['uuid']
            ))
            print(f"  ↻ {tipo_factura:9} | {inv_data['receiver_name'][:30]:30} | ${inv_data['total']:>10,.2f}")
            updated += 1
        else:
            # Insertar nueva
            cursor.execute("""
                INSERT INTO invoice (
                    uuid, company_id, date, total, subtotal, tax, type,
                    issuer_rfc, issuer_name, receiver_rfc, receiver_name,
                    forma_pago, metodo_pago, uso_cfdi, descripcion, xml_content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inv_data['uuid'], company_id, inv_data['date'], 
                inv_data['total'], inv_data['subtotal'], inv_data['tax'], 
                inv_data['type'], inv_data['issuer_rfc'], inv_data['issuer_name'],
                inv_data['receiver_rfc'], inv_data['receiver_name'],
                inv_data['forma_pago'], inv_data['metodo_pago'],
                inv_data['uso_cfdi'], inv_data['descripcion'], inv_data['xml']
            ))
            
            invoice_id = cursor.lastrowid
            
            # Crear Movement
            mov_type = None
            if is_emitted:
                if inv_data['type'] == 'I':
                    mov_type = 'INCOME'
                elif inv_data['type'] == 'E':
                    mov_type = 'EXPENSE'
            else:  # Received
                if inv_data['type'] == 'I':
                    mov_type = 'EXPENSE'
                elif inv_data['type'] == 'E':
                    mov_type = 'INCOME'
            
            if mov_type:
                other_party = inv_data['receiver_rfc'] if is_emitted else inv_data['issuer_rfc']
                cursor.execute("""
                    INSERT INTO movement (
                        invoice_id, company_id, amount, type, description, date
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    invoice_id, company_id, inv_data['total'], mov_type,
                    f"Factura {other_party} ({inv_data['type']})", inv_data['date']
                ))
            
            print(f"  + {tipo_factura:9} | {inv_data['receiver_name'][:30]:30} | ${inv_data['total']:>10,.2f}")
            added += 1
    
    conn.commit()
    conn.close()
    
    print("\n" + "="*80)
    print(f"✓ Carga completada:")
    print(f"  - Nuevas:       {added}")
    print(f"  - Actualizadas: {updated}")
    print(f"  - Total:        {added + updated}")
    print(f"\n  - Emitidas:     {emitidas}")
    print(f"  - Recibidas:    {recibidas}")

if __name__ == "__main__":
    load_invoices()
