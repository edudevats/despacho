import os
from datetime import datetime
from flask import request
from models import Supplier, Invoice
from extensions import db
from utils.timezone_helper import now_mexico

# Define project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def safe_redirect_target(candidate, fallback):
    if not candidate:
        return fallback
    try:
        from urllib.parse import urlparse
        parsed = urlparse(candidate)
    except Exception:
        return fallback
    if parsed.scheme and parsed.scheme not in ('http', 'https'):
        return fallback
    if parsed.netloc and parsed.netloc != request.host:
        return fallback
    return candidate

def find_company_invoice_xml_path(company_rfc, uuid, project_root=None):
    if not company_rfc or not uuid:
        return None
    base_dir = project_root or PROJECT_ROOT
    xml_dir = os.path.join(base_dir, 'xml', company_rfc)
    if not os.path.isdir(xml_dir):
        return None
    target_uuid = uuid.lower()
    for filename in os.listdir(xml_dir):
        if not filename.lower().endswith('.xml'):
            continue
        if filename.lower().startswith('acuse_cancelacion_'):
            continue
        stem = filename[:-4]
        filename_uuid = stem.split('_', 1)[1] if '_' in stem else stem
        if filename_uuid.lower() == target_uuid:
            return os.path.join(xml_dir, filename)
    return None

def parse_invoice_xml_for_db(xml_content, fallback_uuid=None):
    from lxml import etree
    if isinstance(xml_content, bytes):
        xml_bytes = xml_content
        xml_text = xml_content.decode('utf-8', errors='replace')
    else:
        xml_text = xml_content
        xml_bytes = xml_content.encode('utf-8')
    root = etree.fromstring(xml_bytes)
    ns = {
        'cfdi': root.nsmap.get(None) or root.nsmap.get('cfdi') or 'http://www.sat.gob.mx/cfd/4',
        'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
    }
    emisor = root.find('cfdi:Emisor', ns)
    receptor = root.find('cfdi:Receptor', ns)
    timbre = root.find('.//tfd:TimbreFiscalDigital', ns)
    impuestos = root.find('cfdi:Impuestos', ns)
    def as_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    fecha = root.get('Fecha')
    date_value = datetime.fromisoformat(fecha) if fecha else now_mexico()
    tax_value = as_float(impuestos.get('TotalImpuestosTrasladados')) if impuestos is not None else 0.0
    return {
        'uuid': (timbre.get('UUID') if timbre is not None else None) or fallback_uuid,
        'date': date_value,
        'total': as_float(root.get('Total')),
        'subtotal': as_float(root.get('SubTotal')),
        'tax': tax_value,
        'type': root.get('TipoDeComprobante'),
        'issuer_rfc': emisor.get('Rfc') if emisor is not None else None,
        'issuer_name': emisor.get('Nombre') if emisor is not None else None,
        'receiver_rfc': receptor.get('Rfc') if receptor is not None else None,
        'receiver_name': receptor.get('Nombre') if receptor is not None else None,
        'forma_pago': root.get('FormaPago'),
        'metodo_pago': root.get('MetodoPago'),
        'uso_cfdi': receptor.get('UsoCFDI') if receptor is not None else None,
        'xml_content': xml_text,
        'currency': root.get('Moneda'),
        'exchange_rate': as_float(root.get('TipoCambio'), None),
        'exportation': root.get('Exportacion'),
        'version': root.get('Version'),
        'serie': root.get('Serie'),
        'folio': root.get('Folio'),
        'lugar_expedicion': root.get('LugarExpedicion'),
        'no_certificado': root.get('NoCertificado'),
        'sello': root.get('Sello'),
        'certificado': root.get('Certificado'),
        'regimen_fiscal_emisor': emisor.get('RegimenFiscal') if emisor is not None else None,
        'regimen_fiscal_receptor': receptor.get('RegimenFiscalReceptor') if receptor is not None else None,
        'domicilio_fiscal_receptor': receptor.get('DomicilioFiscalReceptor') if receptor is not None else None,
        'fecha_timbrado': datetime.fromisoformat(timbre.get('FechaTimbrado')) if timbre is not None and timbre.get('FechaTimbrado') else None,
        'rfc_prov_certif': timbre.get('RfcProvCertif') if timbre is not None else None,
        'sello_sat': timbre.get('SelloSAT') if timbre is not None else None,
        'no_certificado_sat': timbre.get('NoCertificadoSAT') if timbre is not None else None,
    }

def get_or_create_supplier(company_id, rfc, business_name):
    supplier = Supplier.query.filter_by(company_id=company_id, rfc=rfc).first()
    if not supplier:
        supplier = Supplier(
            company_id=company_id,
            rfc=rfc,
            business_name=business_name or rfc,
            active=True
        )
        db.session.add(supplier)
        db.session.flush()
    else:
        if business_name and len(business_name) > len(supplier.business_name or ''):
            supplier.business_name = business_name
    return supplier

def update_supplier_stats(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier:
        return
    invoices = Invoice.query.filter_by(supplier_id=supplier_id).all()
    if invoices:
        supplier.invoice_count = len(invoices)
        supplier.total_invoiced = sum(inv.total for inv in invoices)
        supplier.first_invoice_date = min(inv.date for inv in invoices)
        supplier.last_invoice_date = max(inv.date for inv in invoices)
    else:
        supplier.invoice_count = 0
        supplier.total_invoiced = 0
        supplier.first_invoice_date = None
        supplier.last_invoice_date = None

def format_currency(value):
    try:
        return "{:,.2f}".format(float(value))
    except (ValueError, TypeError):
        return "0.00"

def chunk_split(body, chunklen=76, end='\\r\\n'):
    if not body: return ""
    return end.join(body[i:i+chunklen] for i in range(0, len(body), chunklen))

from satcfdi.accounting import SatCFDI
from satcfdi.accounting.models import EstadoComprobante

class AppSatCFDI(SatCFDI):
    """
    Subclase de SatCFDI que implementa los métodos abstractos estatus() y fecha_cancelacion
    para evitar NotImplementedError al calcular saldos pendientes y parcialidades.
    """
    def __init__(self, *args, status_sat='VIGENTE', fecha_cancelacion_dt=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._status_sat = status_sat
        self._fecha_cancelacion_dt = fecha_cancelacion_dt

    def estatus(self) -> EstadoComprobante:
        status = getattr(self, '_status_sat', 'VIGENTE')
        if status == 'CANCELADO':
            return EstadoComprobante.CANCELADO
        return EstadoComprobante.VIGENTE

    @property
    def fecha_cancelacion(self):
        return getattr(self, '_fecha_cancelacion_dt', None)


