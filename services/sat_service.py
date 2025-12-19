from satcfdi.pacs.sat import SAT, TipoDescargaMasivaTerceros, EstadoSolicitud, EstadoComprobante
from satcfdi.models import Signer
from datetime import datetime
import time
import zipfile
import io
import base64
import os
from satcfdi.cfdi import CFDI
from satcfdi import render



# SAT Error Codes Map - Moved to module level for reuse
SAT_ERROR_CODES = {
    '300': {
        'mensaje': 'Usuario No Válido',
        'accion': 'Verifique que el RFC y FIEL correspondan a la empresa correcta.'
    },
    '301': {
        'mensaje': 'XML Mal Formado (Información inválida)',
        'accion': 'Verifique que el RFC receptor sea correcto.'
    },
    '302': {
        'mensaje': 'Sello Mal Formado',
        'accion': 'Verifique que los archivos FIEL (.cer y .key) sean válidos.'
    },
    '303': {
        'mensaje': 'Sello no corresponde con RFC Solicitante',
        'accion': 'El FIEL no corresponde al RFC de la empresa. Use el FIEL correcto.'
    },
    '304': {
        'mensaje': 'Certificado Revocado o Caduco',
        'accion': 'Su certificado FIEL ha expirado o fue revocado. Renueve su FIEL en el portal del SAT.'
    },
    '305': {
        'mensaje': 'Certificado Inválido',
        'accion': 'Verifique que esté usando un certificado FIEL válido (no CSD).'
    },
    '5000': {
        'mensaje': 'Solicitud recibida con éxito',
        'accion': 'La solicitud fue procesada correctamente.'
    },
    '5002': {
        'mensaje': 'Se agotaron las solicitudes de por vida para estos parámetros',
        'accion': 'Intente cambiando las fechas de inicio o fin. El SAT limita las consultas por rango de fechas.'
    },
    '5003': {
        'mensaje': 'Tope máximo de elementos excedido',
        'accion': 'Reduzca el rango de fechas para obtener menos facturas por solicitud.'
    },
    '5004': {
        'mensaje': 'No se encontró información',
        'accion': 'No hay facturas en el rango de fechas seleccionado. Verifique las fechas.'
    },
    '5005': {
        'mensaje': 'Solicitud duplicada',
        'accion': 'Ya existe una solicitud en proceso con estos parámetros. Espere unos minutos e intente nuevamente.'
    },
    '5011': {
        'mensaje': 'Límite de descargas diarias alcanzado',
        'accion': 'Ha alcanzado el límite diario de descargas. Intente nuevamente mañana.'
    },
    '404': {
        'mensaje': 'Error no controlado del SAT',
        'accion': 'Intente nuevamente. Si persiste, reporte el problema.'
    }
}


class SATError(Exception):
    """Custom exception for SAT-specific errors with user-friendly messages."""
    
    def __init__(self, code, mensaje=None, accion=None, raw_message=None):
        self.code = str(code)
        error_info = SAT_ERROR_CODES.get(self.code, {
            'mensaje': f'Error desconocido del SAT (Código: {code})',
            'accion': 'Intente nuevamente o contacte soporte técnico.'
        })
        self.mensaje = mensaje or error_info['mensaje']
        self.accion = accion or error_info['accion']
        self.raw_message = raw_message
        super().__init__(f"[{self.code}] {self.mensaje}")
    
    def get_user_message(self):
        """Returns a formatted message for display to the user."""
        return f"Error del SAT ({self.code}): {self.mensaje}. {self.accion}"


class SATService:
    def __init__(self, rfc, fiel_cer, fiel_key, fiel_password):
        self.rfc = rfc
        self.fiel_cer = fiel_cer
        self.fiel_key = fiel_key
        self.fiel_password = fiel_password
        self.sat_api = None

    def _get_signer(self):
        with open(self.fiel_cer, 'rb') as cer_file, open(self.fiel_key, 'rb') as key_file:
            return Signer.load(
                certificate=cer_file.read(),
                key=key_file.read(),
                password=self.fiel_password
            )

    def validate_credentials(self):
        """
        Validate the provided FIEL credentials by loading the signer.
        Returns True if valid, raises Exception otherwise.
        """
        try:
            self._get_signer()
            return True
        except Exception as e:
            raise Exception(f"Invalid FIEL credentials: {str(e)}")

    class Catalogos:
        @staticmethod
        def catTipoComprobante(valor):
            # Valida si es objeto Code de satcfdi o string
            code = valor.code if hasattr(valor, 'code') else str(valor)
            mapa = {
                'I': 'Ingreso',
                'E': 'Egreso',
                'T': 'Traslado',
                'N': 'Nómina',
                'P': 'Pago'
            }
            return f"{code} - {mapa.get(code, '')}"

        @staticmethod
        def catFormaPago(valor):
            code = valor.code if hasattr(valor, 'code') else str(valor)
            return code  # Podríamos agregar mapa completo si se requiere

        @staticmethod
        def catMetodoPago(valor):
            code = valor.code if hasattr(valor, 'code') else str(valor)
            mapa = {'PUE': 'Pago en una sola exhibición', 'PPD': 'Pago en parcialidades o diferido'}
            return f"{code} - {mapa.get(code, '')}"

        @staticmethod
        def catExportacion(valor):
            code = valor.code if hasattr(valor, 'code') else str(valor)
            mapa = {'01': 'No aplica', '02': 'Definitiva', '03': 'Temporal', '04': 'Definitiva con clave distinta'}
            return f"{code} - {mapa.get(code, '')}"

        @staticmethod
        def catPeriodicidad(valor):
            code = valor.code if hasattr(valor, 'code') else str(valor)
            mapa = {'01': 'Diaria', '02': 'Semanal', '03': 'Quincenal', '04': 'Mensual', '05': 'Bimestral'}
            return f"{code} - {mapa.get(code, '')}"
        
        @staticmethod
        def catMeses(valor):
            code = valor.code if hasattr(valor, 'code') else str(valor)
            return code

        @staticmethod
        def catRegimenFiscal(valor):
             code = valor.code if hasattr(valor, 'code') else str(valor)
             return code

        @staticmethod
        def catUsoCFDI(valor):
             code = valor.code if hasattr(valor, 'code') else str(valor)
             return code
        
        @staticmethod
        def catObjetoImp(valor):
             code = valor.code if hasattr(valor, 'code') else str(valor)
             mapa = {'01': 'No objeto de impuesto', '02': 'Sí objeto de impuesto', '03': 'Sí objeto de impuesto y no obligado a desglose', '04': 'Sí objeto de impuesto y no causa impuesto'}
             return f"{code} - {mapa.get(code, '')}"

        @staticmethod
        def catImpuesto(valor):
             code = valor.code if hasattr(valor, 'code') else str(valor)
             mapa = {'001': 'ISR', '002': 'IVA', '003': 'IEPS'}
             return f"{code} - {mapa.get(code, '')}"

    class AttrDict(dict):
        """Helper to allow dot access to dictionary keys."""
        def __getattr__(self, name):
            if name in self:
                return self[name]
            raise AttributeError(f"'AttrDict' object has no attribute '{name}'. Available keys: {list(self.keys())}")
        
        def __setattr__(self, name, value):
             self[name] = value

    @staticmethod
    def generate_pdf(xml_content):
        """
        Genera PDF bytes desde contenido XML usando satcfdi.
        Esta implementación usa la librería satcfdi que genera PDFs de alta calidad
        con formato profesional para facturas mexicanas (CFDI).
        
        Args:
            xml_content: Contenido XML del CFDI (string o bytes)
            
        Returns:
            bytes: Contenido del PDF generado
        """
        if isinstance(xml_content, bytes):
            xml_content = xml_content.decode('utf-8')
        
        # Cargar el CFDI desde el XML
        cfdi = CFDI.from_string(xml_content)
        
        # Generar PDF usando satcfdi render
        # pdf_bytes retorna los bytes del PDF directamente
        pdf_content = render.pdf_bytes(cfdi)
        
        return pdf_content




    def _process_bulk_download(self, request_id):
        """
        Helper to poll status and download packages for a given request_id.
        """
        results = []
        max_retries = 30
        
        print(f"Polling status for Request ID: {request_id}")
        
        for _ in range(max_retries):
            status_response = self.sat_api.recover_comprobante_status(request_id)
            state = status_response.get('EstadoSolicitud')
            code_state = status_response.get('CodigoEstadoSolicitud')
            
            print(f"Status: {state}, Code: {code_state}")

            # Check using Enum or integer values (satcfdi returns int values mostly)
            if state == EstadoSolicitud.TERMINADA or state == 3 or state == 'Terminado':
                # 3. Download Packages
                package_ids = status_response.get('IdsPaquetes', []) 
                if not package_ids:
                     package_ids = status_response.get('Paquetes', [])

                print(f"Request {request_id} Finished. Found {len(package_ids)} packages.")
                
                if not package_ids:
                    print("WARNING: SAT Request finished but returned NO packages (0 invoices).")
                    return []

                for pkg_id in package_ids:
                    print(f"Downloading Package ID: {pkg_id}...")
                    max_download_retries = 3
                    for retry in range(max_download_retries):
                        try:
                            response, paquete_b64 = self.sat_api.recover_comprobante_download(id_paquete=pkg_id)
                            
                            # Check if package data is None
                            if paquete_b64 is None:
                                print(f"WARNING: Package {pkg_id} returned None (retry {retry+1}/{max_download_retries})")
                                if retry < max_download_retries - 1:
                                    time.sleep(5)  # Wait before retry
                                    continue
                                else:
                                    print(f"ERROR: Package {pkg_id} consistently returned None after {max_download_retries} retries")
                                    break
                            
                            # Decode base64
                            zip_data = base64.b64decode(paquete_b64)
                            
                            # 4. Unzip and Parse
                            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                                for filename in z.namelist():
                                    if filename.endswith('.xml'):
                                        xml_content = z.read(filename)
                                        parsed = self._parse_xml_bytes(xml_content)
                                        if parsed:
                                            results.append(parsed)
                            break  # Success, exit retry loop
                        except Exception as e:
                            print(f"Error downloading/processing package {pkg_id} (retry {retry+1}): {e}")
                            if retry < max_download_retries - 1:
                                time.sleep(5)
                            # Continue to next retry or package instead of failing all
                
                print(f"Successfully processed {len(results)} invoices from packages.")
                return results
            
            elif state == EstadoSolicitud.RECHAZADA or state == 5 or state == 'Rechazada':
                # Use the module-level SAT_ERROR_CODES and SATError exception
                code_str = str(code_state) if code_state else 'unknown'
                print(f"SAT rechazó la solicitud. Código: {code_str}")
                raise SATError(code=code_str, raw_message=f"EstadoSolicitud: {state}")
            
            time.sleep(10) # Wait 10 seconds before next check
        
        raise Exception("Download timed out.")

    def download_received_invoices(self, start_date, end_date):
        """
        Download received invoices (CFDI) for a date range using FIEL.
        Based on satcfdi documentation.
        """
        signer = self._get_signer()
        self.sat_api = SAT(signer=signer)
        
        # Request download - using signer.rfc as shown in documentation
        response = self.sat_api.recover_comprobante_received_request(
            fecha_inicial=start_date,
            fecha_final=end_date,
            rfc_receptor=signer.rfc,  # Use signer.rfc as per documentation
            tipo_solicitud=TipoDescargaMasivaTerceros.CFDI,
            estado_comprobante=EstadoComprobante.VIGENTE
        )
        
        print(f"SAT Received Request Response: {response}")
        
        request_id = response.get('IdSolicitud')
        if not request_id:
            code = response.get('CodEstatus') or response.get('CodigoEstadoSolicitud')
            msg = response.get('Mensaje') or response.get('MensajeError') or str(response)
            raise Exception(f"SAT no aceptó la solicitud. Código: {code}, Mensaje: {msg}")

        return self._process_bulk_download(request_id)

    def download_emitted_invoices(self, start_date, end_date):
        """
        Download emitted invoices (CFDI) for a date range using FIEL.
        Based on satcfdi documentation.
        """
        signer = self._get_signer()
        self.sat_api = SAT(signer=signer)
        
        # Request download - for emitted invoices, we are the emisor
        # Note: Documentation shows rfc_receptor but for emitted invoices
        # we filter by our RFC as the issuer
        response = self.sat_api.recover_comprobante_emitted_request(
            fecha_inicial=start_date,
            fecha_final=end_date,
            rfc_emisor=signer.rfc,  # We are the issuer for emitted invoices
            tipo_solicitud=TipoDescargaMasivaTerceros.CFDI
        )
        
        print(f"SAT Emitted Request Response: {response}")
        
        request_id = response.get('IdSolicitud')
        if not request_id:
            code = response.get('CodEstatus') or response.get('CodigoEstadoSolicitud')
            msg = response.get('Mensaje') or response.get('MensajeError') or str(response)
            raise Exception(f"SAT no aceptó la solicitud. Código: {code}, Mensaje: {msg}")

        return self._process_bulk_download(request_id)

    def _parse_xml_bytes(self, xml_content):
        from satcfdi.cfdi import CFDI
        try:
            cfdi = CFDI.from_string(xml_content)
            
            # Handle Complemento - it can be a list or a dict
            complemento = cfdi.get('Complemento', {})
            if isinstance(complemento, list):
                # If it's a list, search for TimbreFiscalDigital in each item
                uuid = None
                for comp in complemento:
                    if isinstance(comp, dict):
                        tfd = comp.get('TimbreFiscalDigital', {})
                        if isinstance(tfd, dict):
                            uuid = tfd.get('UUID')
                        elif isinstance(tfd, list) and len(tfd) > 0:
                            uuid = tfd[0].get('UUID') if isinstance(tfd[0], dict) else None
                        if uuid:
                            break
            elif isinstance(complemento, dict):
                tfd = complemento.get('TimbreFiscalDigital', {})
                if isinstance(tfd, dict):
                    uuid = tfd.get('UUID')
                elif isinstance(tfd, list) and len(tfd) > 0:
                    uuid = tfd[0].get('UUID') if isinstance(tfd[0], dict) else None
                else:
                    uuid = None
            else:
                uuid = None
                
            if not uuid:
                return None

            total = float(cfdi.get('Total', 0))
            subtotal = float(cfdi.get('SubTotal', 0))
            tax = total - subtotal

            fecha_obj = cfdi['Fecha']
            if isinstance(fecha_obj, str):
                if 'T' in fecha_obj:
                    date = datetime.fromisoformat(fecha_obj.replace('Z', '+00:00'))
                else:
                    date = datetime.strptime(fecha_obj, '%Y-%m-%d')
            else:
                 # It's already a datetime object
                 date = fecha_obj

            # Extract the type code as a simple string (e.g., 'I' or 'E')
            tipo_comprobante = cfdi.get('TipoDeComprobante')
            if tipo_comprobante is not None and hasattr(tipo_comprobante, 'code'):
                tipo_str = tipo_comprobante.code
            else:
                tipo_str = str(tipo_comprobante) if tipo_comprobante else None

            # Extract additional fields - handle potential list types
            emisor = cfdi.get('Emisor', {})
            if isinstance(emisor, list) and len(emisor) > 0:
                emisor = emisor[0] if isinstance(emisor[0], dict) else {}
            elif not isinstance(emisor, dict):
                emisor = {}
                
            receptor = cfdi.get('Receptor', {})
            if isinstance(receptor, list) and len(receptor) > 0:
                receptor = receptor[0] if isinstance(receptor[0], dict) else {}
            elif not isinstance(receptor, dict):
                receptor = {}
            
            # Get forma_pago and metodo_pago (they may also be Code objects)
            forma_pago = cfdi.get('FormaPago')
            if forma_pago is not None and hasattr(forma_pago, 'code'):
                forma_pago = forma_pago.code
            elif forma_pago is not None:
                forma_pago = str(forma_pago)
            
            metodo_pago = cfdi.get('MetodoPago')
            if metodo_pago is not None and hasattr(metodo_pago, 'code'):
                metodo_pago = metodo_pago.code
            elif metodo_pago is not None:
                metodo_pago = str(metodo_pago)
            
            uso_cfdi = receptor.get('UsoCFDI')
            if uso_cfdi is not None and hasattr(uso_cfdi, 'code'):
                uso_cfdi = uso_cfdi.code
            elif uso_cfdi is not None:
                uso_cfdi = str(uso_cfdi)
            
            # Get description from first concept
            conceptos = cfdi.get('Conceptos', {})
            descripcion = None
            if conceptos:
                # Handle different possible structures for Conceptos
                if isinstance(conceptos, list):
                    # If Conceptos itself is a list
                    if len(conceptos) > 0:
                        first_concepto = conceptos[0]
                        if isinstance(first_concepto, dict):
                            descripcion = first_concepto.get('Descripcion', '')
                elif isinstance(conceptos, dict):
                    # conceptos is a dict with 'Concepto' key
                    concepto = conceptos.get('Concepto', [])
                    if isinstance(concepto, list) and len(concepto) > 0:
                        if isinstance(concepto[0], dict):
                            descripcion = concepto[0].get('Descripcion', '')
                    elif isinstance(concepto, dict):
                        descripcion = concepto.get('Descripcion', '')

            # Extract Global Information (CFDI 4.0)
            informacion_global = cfdi.get('InformacionGlobal', {})
            periodicidad = None
            meses = None
            anio = None
            if informacion_global:
                periodicidad = informacion_global.get('Periodicidad')
                # Convert Code object to string if needed
                if periodicidad is not None and hasattr(periodicidad, 'code'):
                    periodicidad = periodicidad.code
                elif periodicidad is not None:
                    periodicidad = str(periodicidad)
                
                meses = informacion_global.get('Meses')
                # Convert Code object to string if needed
                if meses is not None and hasattr(meses, 'code'):
                    meses = meses.code
                elif meses is not None:
                    meses = str(meses)
                
                anio = informacion_global.get('Año')
                # Convert to int or string if needed
                if anio is not None:
                    try:
                        anio = int(anio)
                    except (ValueError, TypeError):
                        anio = None

            # Extract other fields
            condiciones_de_pago = cfdi.get('CondicionesDePago')
            if condiciones_de_pago is not None and hasattr(condiciones_de_pago, 'code'):
                condiciones_de_pago = condiciones_de_pago.code
            elif condiciones_de_pago is not None:
                condiciones_de_pago = str(condiciones_de_pago)
            
            moneda = cfdi.get('Moneda')
            if moneda is not None and hasattr(moneda, 'code'):
                moneda = moneda.code
            elif moneda is not None:
                moneda = str(moneda)
            
            tipo_cambio = cfdi.get('TipoCambio')
            if tipo_cambio:
                try:
                    tipo_cambio = float(tipo_cambio)
                except:
                    tipo_cambio = None
            
            exportacion = cfdi.get('Exportacion')
            if exportacion is not None and hasattr(exportacion, 'code'):
                exportacion = exportacion.code
            elif exportacion is not None:
                exportacion = str(exportacion)
            
            version = cfdi.get('Version')
            if version is not None and hasattr(version, 'code'):
                version = version.code
            elif version is not None:
                version = str(version)

            return {
                'uuid': uuid,
                'date': date,
                'total': total,
                'subtotal': subtotal,
                'tax': tax,
                'type': tipo_str,
                'issuer_rfc': emisor.get('Rfc'),
                'issuer_name': emisor.get('Nombre'),
                'receiver_rfc': receptor.get('Rfc'),
                'receiver_name': receptor.get('Nombre'),
                'forma_pago': forma_pago,
                'metodo_pago': metodo_pago,
                'uso_cfdi': uso_cfdi,
                'descripcion': descripcion,
                'xml': xml_content.decode('utf-8'),
                # New fields
                'periodicity': periodicidad,
                'months': meses,
                'fiscal_year': anio,
                'payment_terms': condiciones_de_pago,
                'currency': moneda,
                'exchange_rate': tipo_cambio,
                'exportation': exportacion,
                'version': version
            }
        except Exception as e:
            print(f"Error parsing XML: {e}")
            return None

    def download_csf(self):
        """
        CSF download requires CIEC, which is not supported securely/stably right now.
        Use of SATFacturaElectronica could be investigated for validation, but not download.
        """
        raise NotImplementedError("CSF download is not supported with current library version.")


