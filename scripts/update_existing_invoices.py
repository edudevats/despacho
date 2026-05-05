import sqlite3
import os
import sys
from satcfdi.cfdi import CFDI

# Add project root to path to import models if needed
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

# Definir rutas correctas (asumiendo que el script está en /scripts y la app en la raíz)
db_path = os.path.join(project_root, 'instance', 'sat_app.db')
facturas_dir = os.path.join(project_root, 'facturas')

def extract_code_value(code_obj):
    """Extrae el valor de un objeto Code de satcfdi"""
    if code_obj is None:
        return None
    code_str = str(code_obj)
    if "'" in code_str:
        return code_str.split("'")[1]
    return code_str

def update_invoices():
    print(f"Conectando a base de datos en: {db_path}")
    print(f"Buscando facturas en: {facturas_dir}")

    if not os.path.exists(db_path):
        print("Error: No se encuentra la base de datos.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Obtener facturas. 
    # Modificamos la query para buscar aquellas donde version es NULL
    # Esto permite actualizar registros antiguos que ya tengan issuer_name pero les falte version
    try:
        cursor.execute("SELECT id, uuid, company_id FROM invoice WHERE version IS NULL")
        invoices = cursor.fetchall()
    except sqlite3.OperationalError:
        # Si la columna version no existe, fallará. Asumimos que la migración ya corrió.
        print("Error: La columna 'version' no parece existir. Asegúrate de correr la migración primero.")
        return
    
    print(f"Encontradas {len(invoices)} facturas para actualizar (version IS NULL)...")
    
    cursor.execute("SELECT id, name FROM company")
    companies = {row[0]: row[1] for row in cursor.fetchall()}
    
    updated = 0
    for inv_id, uuid, company_id in invoices:
        # Buscar el archivo XML
        xml_path = None
        
        found = False
        for company_folder in os.listdir(facturas_dir):
            potential_path = os.path.join(facturas_dir, company_folder, f"{uuid}.xml")
            if os.path.exists(potential_path):
                xml_path = potential_path
                found = True
                break
        
        if not found:
            # print(f"  ✗ XML no encontrado para {uuid}")
            continue
        
        try:
            with open(xml_path, 'rb') as f:
                content = f.read()
                cfdi = CFDI.from_string(content)
            
            # --- Extracción de Datos ---
            version = cfdi.get('Version')
            
            # Emisor/Receptor
            emisor = cfdi.get('Emisor', {})
            receptor = cfdi.get('Receptor', {})
            issuer_name = emisor.get('Nombre')
            receiver_name = receptor.get('Nombre')
            
            # Formatos de pago
            forma_pago = extract_code_value(cfdi.get('FormaPago'))
            metodo_pago = extract_code_value(cfdi.get('MetodoPago'))
            uso_cfdi = extract_code_value(receptor.get('UsoCFDI'))
            
            # Descripción
            descripcion = None
            conceptos = cfdi.get('Conceptos', {})
            if isinstance(conceptos, list) and conceptos:
                 first = conceptos[0]
                 if isinstance(first, dict): descripcion = first.get('Descripcion')
            elif isinstance(conceptos, dict):
                 # Check inner Concepto
                 conc = conceptos.get('Concepto')
                 if isinstance(conc, list) and conc:
                     descripcion = conc[0].get('Descripcion') if isinstance(conc[0], dict) else None
                 elif isinstance(conc, dict):
                     descripcion = conc.get('Descripcion')

            # --- Nuevos Campos CFDI 4.0 / Global ---
            informacion_global = cfdi.get('InformacionGlobal', {})
            periodicidad = extract_code_value(informacion_global.get('Periodicidad'))
            meses = extract_code_value(informacion_global.get('Meses'))
            anio = informacion_global.get('Año')
            
            condiciones_de_pago = cfdi.get('CondicionesDePago')
            moneda = extract_code_value(cfdi.get('Moneda'))
            tipo_cambio = cfdi.get('TipoCambio')
            if tipo_cambio:
                try: tipo_cambio = float(tipo_cambio)
                except: tipo_cambio = None
                
            exportacion = extract_code_value(cfdi.get('Exportacion'))

            # Actualizar DB
            cursor.execute("""
                UPDATE invoice 
                SET issuer_name = ?, receiver_name = ?, forma_pago = ?, 
                    metodo_pago = ?, uso_cfdi = ?, descripcion = ?,
                    version = ?, periodicity = ?, months = ?, fiscal_year = ?,
                    payment_terms = ?, currency = ?, exchange_rate = ?, exportation = ?
                WHERE id = ?
            """, (
                issuer_name, receiver_name, forma_pago, metodo_pago, uso_cfdi, descripcion,
                version, periodicidad, meses, anio,
                condiciones_de_pago, moneda, tipo_cambio, exportacion,
                inv_id
            ))
            
            updated += 1
            if updated % 10 == 0:
                print(f"  ✓ Procesadas {updated} facturas...")
                
        except Exception as e:
            print(f"  ✗ Error procesando {uuid}: {e}")

    conn.commit()
    conn.close()
    
    print(f"\n✓ Actualización completada. Total actualizados: {updated}")

if __name__ == "__main__":
    update_invoices()
