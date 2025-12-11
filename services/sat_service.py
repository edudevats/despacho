from satcfdi.pacs.sat import SAT, TipoDescargaMasivaTerceros, EstadoSolicitud, EstadoComprobante
from satcfdi.models import Signer
from datetime import datetime
import time
import zipfile
import io
import base64

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
                # SAT Error Codes Map
                SAT_ERRORS = {
                    '300': 'Usuario No Válido',
                    '301': 'XML Mal Formado (Información inválida, ej. RFC receptor)',
                    '302': 'Sello Mal Formado',
                    '303': 'Sello no corresponde con RFC Solicitante',
                    '304': 'Certificado Revocado o Caduco',
                    '305': 'Certificado Inválido',
                    '5000': 'Solicitud recibida con éxito',
                    '5002': 'Se agotaron las solicitudes "de por vida" para estos parámetros. Intente cambiando fechas.',
                    '5003': 'Tope máximo de elementos excedido por solicitud',
                    '5004': 'No se encontró información para la solicitud',
                    '5005': 'Solicitud duplicada (Ya existe una solicitud vigente con estos parámetros)',
                    '5011': 'Se ha alcanzado el límite de descargas diarias por folio',
                    '404': 'Error no controlado (Intente nuevamente o reporte RMA)'
                }
                
                reason = SAT_ERRORS.get(str(code_state), f"Código SAT desconocido: {code_state}")
                if code_state == 'Solicitud rechazada': 
                     reason = f"{code_state} (Verifique permisos/fechas)"
                
                error_msg = f"SAT rechazó la solicitud ({code_state}): {reason}"
                print(error_msg)
                raise Exception(error_msg)
            
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


