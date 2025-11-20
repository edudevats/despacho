"""
Parser de archivos XML CFDI
Extrae datos fiscales de facturas electrónicas
"""
from lxml import etree
from decimal import Decimal
from datetime import datetime

# Namespaces comunes en CFDI 3.3 y 4.0
NAMESPACES = {
    'cfdi': 'http://www.sat.gob.mx/cfd/3',
    'cfdi4': 'http://www.sat.gob.mx/cfd/4',
    'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
}


def parse_xml_cfdi(xml_path):
    """
    Parsea un archivo XML CFDI y extrae los datos principales

    Args:
        xml_path: Ruta al archivo XML

    Returns:
        dict con datos del CFDI o None si hay error
    """
    try:
        tree = etree.parse(xml_path)
        root = tree.getroot()

        # Determinar versión CFDI (3.3 o 4.0)
        version = root.get('Version') or root.get('version')
        ns_cfdi = 'cfdi4' if version == '4.0' else 'cfdi'

        # Extraer datos del comprobante
        datos = {
            'version': version,
            'serie': root.get('Serie') or root.get('serie') or '',
            'folio': root.get('Folio') or root.get('folio') or '',
            'fecha_emision': parse_fecha(root.get('Fecha') or root.get('fecha')),
            'tipo_comprobante': root.get('TipoDeComprobante') or root.get('tipoDeComprobante'),
            'metodo_pago': root.get('MetodoPago') or root.get('metodoPago') or '',
            'forma_pago': root.get('FormaPago') or root.get('formaPago') or '',
            'moneda': root.get('Moneda') or root.get('moneda') or 'MXN',
            'tipo_cambio': Decimal(root.get('TipoCambio') or root.get('tipoCambio') or '1'),
        }

        # Extraer datos del emisor
        emisor = root.find(f'{{{NAMESPACES[ns_cfdi]}}}Emisor')
        if emisor is not None:
            datos['emisor_rfc'] = emisor.get('Rfc') or emisor.get('rfc')
            datos['emisor_nombre'] = emisor.get('Nombre') or emisor.get('nombre') or ''
            datos['emisor_regimen'] = emisor.get('RegimenFiscal') or emisor.get('regimenFiscal') or ''

        # Extraer datos del receptor
        receptor = root.find(f'{{{NAMESPACES[ns_cfdi]}}}Receptor')
        if receptor is not None:
            datos['receptor_rfc'] = receptor.get('Rfc') or receptor.get('rfc')
            datos['receptor_nombre'] = receptor.get('Nombre') or receptor.get('nombre') or ''
            datos['receptor_uso_cfdi'] = receptor.get('UsoCFDI') or receptor.get('usoCFDI') or ''

        # Extraer importes
        datos['subtotal'] = Decimal(root.get('SubTotal') or root.get('subTotal') or '0')
        datos['descuento'] = Decimal(root.get('Descuento') or root.get('descuento') or '0')
        datos['total'] = Decimal(root.get('Total') or root.get('total') or '0')

        # Extraer impuestos
        impuestos = extract_impuestos(root, ns_cfdi)
        datos.update(impuestos)

        # Extraer UUID del timbre fiscal
        uuid = extract_uuid(root)
        if uuid:
            datos['uuid'] = uuid
            datos['fecha_timbrado'] = extract_fecha_timbrado(root)
        else:
            return None  # Sin UUID no es un CFDI válido

        return datos

    except Exception as e:
        print(f"Error parsing CFDI: {str(e)}")
        return None


def extract_impuestos(root, ns_cfdi):
    """Extrae información de impuestos"""
    impuestos = {
        'iva': Decimal('0'),
        'ieps': Decimal('0'),
        'isr_retenido': Decimal('0'),
        'iva_retenido': Decimal('0'),
    }

    try:
        impuestos_node = root.find(f'{{{NAMESPACES[ns_cfdi]}}}Impuestos')
        if impuestos_node is None:
            return impuestos

        # IVA trasladado
        traslados = impuestos_node.find(f'{{{NAMESPACES[ns_cfdi]}}}Traslados')
        if traslados is not None:
            for traslado in traslados.findall(f'{{{NAMESPACES[ns_cfdi]}}}Traslado'):
                impuesto = traslado.get('Impuesto') or traslado.get('impuesto')
                importe = Decimal(traslado.get('Importe') or traslado.get('importe') or '0')

                if impuesto == '002':  # IVA
                    impuestos['iva'] += importe
                elif impuesto == '003':  # IEPS
                    impuestos['ieps'] += importe

        # Retenciones
        retenciones = impuestos_node.find(f'{{{NAMESPACES[ns_cfdi]}}}Retenciones')
        if retenciones is not None:
            for retencion in retenciones.findall(f'{{{NAMESPACES[ns_cfdi]}}}Retencion'):
                impuesto = retencion.get('Impuesto') or retencion.get('impuesto')
                importe = Decimal(retencion.get('Importe') or retencion.get('importe') or '0')

                if impuesto == '001':  # ISR
                    impuestos['isr_retenido'] += importe
                elif impuesto == '002':  # IVA
                    impuestos['iva_retenido'] += importe

    except Exception as e:
        print(f"Error extrayendo impuestos: {str(e)}")

    return impuestos


def extract_uuid(root):
    """Extrae el UUID del timbre fiscal digital"""
    try:
        # Buscar complemento de timbre
        complemento = root.find(f'{{{NAMESPACES["cfdi"]}}}Complemento') or \
                     root.find(f'{{{NAMESPACES["cfdi4"]}}}Complemento')

        if complemento is not None:
            timbre = complemento.find(f'{{{NAMESPACES["tfd"]}}}TimbreFiscalDigital')
            if timbre is not None:
                return timbre.get('UUID')
    except:
        pass
    return None


def extract_fecha_timbrado(root):
    """Extrae la fecha de timbrado"""
    try:
        complemento = root.find(f'{{{NAMESPACES["cfdi"]}}}Complemento') or \
                     root.find(f'{{{NAMESPACES["cfdi4"]}}}Complemento')

        if complemento is not None:
            timbre = complemento.find(f'{{{NAMESPACES["tfd"]}}}TimbreFiscalDigital')
            if timbre is not None:
                fecha_str = timbre.get('FechaTimbrado')
                if fecha_str:
                    return parse_fecha(fecha_str)
    except:
        pass
    return None


def parse_fecha(fecha_str):
    """Convierte string de fecha ISO a datetime"""
    if not fecha_str:
        return None
    try:
        # Manejar diferentes formatos
        if 'T' in fecha_str:
            return datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
        else:
            return datetime.strptime(fecha_str, '%Y-%m-%d')
    except:
        return None


def validar_rfc(rfc):
    """
    Valida formato de RFC mexicano

    Args:
        rfc: String con el RFC

    Returns:
        bool: True si es válido
    """
    import re
    if not rfc:
        return False

    rfc = rfc.upper().strip()

    # Persona física: 13 caracteres (4 letras + 6 dígitos + 3 alfanuméricos)
    # Persona moral: 12 caracteres (3 letras + 6 dígitos + 3 alfanuméricos)
    pattern_fisica = r'^[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}$'
    pattern_moral = r'^[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}$'

    return re.match(pattern_fisica, rfc) is not None or re.match(pattern_moral, rfc) is not None
