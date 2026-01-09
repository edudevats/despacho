"""
Servicio de Facturación con integración Finkok
Proporciona funcionalidades para timbrado, consulta de estado y verificación de contribuyentes.
"""

from satcfdi.pacs.finkok import Finkok, Environment
from satcfdi.pacs import Accept
from satcfdi.pacs.sat import SAT
from satcfdi.cfdi import CFDI
from satcfdi.models import Signer
from satcfdi.pacs import TaxpayerStatus
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, date
import io
import os
import time
import csv
import requests
from itertools import islice
from satcfdi.pacs import sat

# --- Monkeypatch for encoding issue in satcfdi ---
# The original function forces 'windows-1250' which crashes with some characters.
# We replace it with a version that uses 'latin-1' (common for SAT) or safe fallback.
def _patched_get_listado_69b(refresh_time=sat.REFRESH_TIME):
    try:
        t = os.path.getmtime(sat.LISTADO_COMPLETO_69B_JSON)
    except FileNotFoundError:
        t = -refresh_time

    if time.time() > t + refresh_time:
        try:
            r = requests.get(
                url="http://omawww.sat.gob.mx/cifras_sat/Documents/Listado_Completo_69-B.csv",
                headers={
                    "User-Agent": sat.__version__.__user_agent__
                },
                timeout=30 # Add timeout for safety
            )

            if r.status_code == 200:
                # FIX: Try multiple encodings or use safer decoding
                try:
                    # Try latin-1 which is common for Mexican govt CSVs
                    content_str = r.content.decode('latin-1')
                except UnicodeError:
                    # Fallback to utf-8 with replace
                    content_str = r.content.decode('utf-8', errors='replace')
                
                lines = content_str.splitlines(keepends=True)
                cvs_reader = csv.reader(islice(lines, 3, None), delimiter=',', quotechar='"')
                res = {row[1]: row[3] for row in cvs_reader}
                sat._save_listado_69b(res)
                return res

            sat.logger.error("Unable to get latest Listado 69B, status code: %s", r.status_code)
        except Exception as e:
            sat.logger.error(f"Error updating Listado 69B: {e}")
            # If update fails, try to load existing cache if available
            if t <= 0:
                raise

    if t > 0:
        return sat._load_listado_69b()
    else:
        raise sat.ResponseError("Unable to load Listado Completo 69B")

# Apply patch
sat._get_listado_69b = _patched_get_listado_69b
# ------------------------------------------------

logger = logging.getLogger(__name__)


class FacturacionService:
    """
    Servicio principal de facturación que integra Finkok PAC y servicios del SAT.
    """
    
    def __init__(self, finkok_username: Optional[str] = None, finkok_password: Optional[str] = None, 
                 environment: str = 'TEST', signer: Optional[Signer] = None):
        """
        Inicializa el servicio de facturación.
        
        Args:
            finkok_username: Usuario de Finkok (opcional si solo se usan métodos SAT)
            finkok_password: Contraseña o token de Finkok
            environment: 'TEST' o 'PRODUCTION'
            signer: Objeto Signer con FIEL para operaciones SAT
        """
        self.finkok_username = finkok_username
        self.finkok_password = finkok_password
        self.environment = Environment.TEST if environment.upper() == 'TEST' else Environment.PRODUCTION
        self.signer = signer
        self._finkok_client = None
        self._sat_client = None
    
    def _get_finkok_client(self) -> Finkok:
        """
        Obtiene o crea el cliente de Finkok.
        
        Returns:
            Finkok: Cliente configurado
            
        Raises:
            ValueError: Si las credenciales no están configuradas
        """
        if not self.finkok_username or not self.finkok_password:
            raise ValueError("Credenciales de Finkok no configuradas. Configure las credenciales primero.")
        
        if not self._finkok_client:
            self._finkok_client = Finkok(
                username=self.finkok_username,
                password=self.finkok_password,
                environment=self.environment
            )
        
        return self._finkok_client
    
    def _get_sat_client(self) -> SAT:
        """
        Obtiene o crea el cliente SAT.
        
        Returns:
            SAT: Cliente configurado
            
        Raises:
            ValueError: Si el signer no está configurado
        """
        if not self.signer:
            raise ValueError("FIEL (Signer) no configurado para operaciones SAT.")
        
        if not self._sat_client:
            self._sat_client = SAT(signer=self.signer)
        
        return self._sat_client
    
    def timbrar_factura(self, cfdi_obj, accept: str = 'XML') -> Dict[str, Any]:
        """
        Timbra una factura CFDI con Finkok.
        
        Args:
            cfdi_obj: Objeto CFDI firmado (de satcfdi.cfdi.CFDI)
            accept: Formato de respuesta ('XML', 'PDF', 'XML_PDF')
            
        Returns:
            Dict con success, uuid, xml, pdf (según accept), fecha_timbrado, message
        """
        try:
            logger.info("Iniciando timbrado de factura con Finkok")
            
            # Configurar el tipo de aceptación
            accept_map = {
                'XML': Accept.XML,
                'PDF': Accept.PDF,
                'XML_PDF': Accept.XML_PDF
            }
            accept_type = accept_map.get(accept, Accept.XML_PDF)
            
            # Obtener cliente y timbrar
            pac = self._get_finkok_client()
            doc = pac.stamp(cfdi_obj, accept=accept_type)
            
            # Parsear el XML timbrado para obtener información
            cfdi = CFDI.from_string(doc.xml)
            # Acceder al Timbre Fiscal Digital mediante claves de diccionario
            tfd = cfdi['Complemento']['TimbreFiscalDigital']
            uuid = tfd['UUID']
            fecha_timbrado = tfd['FechaTimbrado']
            
            result = {
                'success': True,
                'message': 'Factura timbrada exitosamente',
                'uuid': uuid,
                'fecha_timbrado': fecha_timbrado,
            }
            
            # Agregar XML si está disponible
            if doc.xml:
                result['xml'] = doc.xml
            
            # Agregar PDF si está disponible
            if hasattr(doc, 'pdf') and doc.pdf:
                result['pdf'] = doc.pdf
            
            logger.info(f"Factura timbrada exitosamente. UUID: {uuid}")
            return result
            
        except Exception as e:
            logger.error(f"Error al timbrar factura: {str(e)}")
            return {
                'success': False,
                'message': f'Error al timbrar: {str(e)}',
                'error': str(e)
            }
    
    def consultar_estado(self, cfdi_xml: Optional[str] = None, uuid: Optional[str] = None,
                        rfc_emisor: Optional[str] = None, rfc_receptor: Optional[str] = None,
                        total: Optional[float] = None) -> Dict[str, Any]:
        """
        Consulta el estado de un CFDI ante el SAT.
        
        Args:
            cfdi_xml: XML del CFDI completo (opcional)
            uuid: UUID del comprobante (requerido si no se proporciona cfdi_xml)
            rfc_emisor: RFC del emisor (requerido si no se proporciona cfdi_xml)
            rfc_receptor: RFC del receptor (requerido si no se proporciona cfdi_xml)
            total: Total del comprobante (requerido si no se proporciona cfdi_xml)
            
        Returns:
            Dict con información del estado del CFDI
        """
        try:
            logger.info(f"Consultando estado de CFDI")
            
            sat = SAT()  # No requiere FIEL para consulta de estado
            
            if cfdi_xml:
                # Consultar desde XML completo
                if isinstance(cfdi_xml, str):
                    cfdi_xml = cfdi_xml.encode('utf-8')
                cfdi = CFDI.from_string(cfdi_xml)
                res = sat.status(cfdi=cfdi)
            else:
                # Consultar con parámetros individuales
                if not all([uuid, rfc_emisor, rfc_receptor, total]):
                    raise ValueError("Se requiere UUID, RFC emisor, RFC receptor y total si no se proporciona el XML")
                
                res = sat.status(
                    uuid=uuid,
                    rfc_emisor=rfc_emisor,
                    rfc_receptor=rfc_receptor,
                    total=total
                )
            
            logger.info(f"Respuesta SAT status type: {type(res)}")
            logger.info(f"Respuesta SAT status content: {res}")

            # Convertir resultado a dict
            # La respuesta del SAT usa llaves con mayúscula inicial
            result = {
                'success': True,
                'estado': res.get('Estado', res.get('estado', 'Desconocido')),
                'es_cancelable': res.get('EsCancelable', res.get('es_cancelable', 'Desconocido')),
                'codigo_estado': res.get('CodigoEstatus', res.get('codigo_estado', 'Desconocido')),
                'validacion_efos': res.get('ValidacionEFOS', res.get('validacion_efos')),
            }
            
            logger.info(f"Estado consultado: {result['estado']}")
            return result
            
        except Exception as e:
            logger.error(f"Error al consultar estado: {str(e)}")
            return {
                'success': False,
                'message': f'Error al consultar estado: {str(e)}',
                'error': str(e)
            }
    
    def verificar_lista_69b(self, rfc: str) -> Dict[str, Any]:
        """
        Verifica si un RFC está en la lista 69B del SAT (contribuyentes definitivos).
        
        Args:
            rfc: RFC a verificar
            
        Returns:
            Dict con el estatus del contribuyente
        """
        try:
            logger.info(f"Verificando RFC {rfc} en lista 69B")
            
            sat = SAT()  # No requiere FIEL
            try:
                # sat.list_69b returns TaxpayerStatus enum or None
                res = sat.list_69b(rfc)
            except UnicodeDecodeError:
                # Retry with cleaned up cache if needed, though monkeypatch should handle it
                # force reload?
                logger.warning("Retrying list_69b after potential encoding error")
                res = sat.list_69b(rfc)
            
            if res is None:
                status_desc = 'NO_ENCONTRADO'
            else:
                # res is a TaxpayerStatus enum
                status_desc = res.name
            
            # Descripciones para el usuario
            descriptions = {
                'DEFINITIVO': 'El RFC está en la lista 69B (contribuyente con operaciones presuntamente inexistentes)',
                'PRESUNTO': 'El RFC está clasificado como PRESUNTO en la lista 69B',
                'SENTENCIA_FAVORABLE': 'El RFC tiene SENTENCIA FAVORABLE en lista 69B',
                'DESVIRTUADO': 'El RFC ha DESVIRTUADO la presunción en lista 69B',
                'NO_ENCONTRADO': 'El RFC no fue encontrado en el padrón del SAT (Limpio)',
                'DESCONOCIDO': 'Estado desconocido'
            }
            
            result = {
                'success': True,
                'rfc': rfc,
                'status': status_desc,
                'descripcion': descriptions.get(status_desc, 'Estado desconocido'),
                'en_lista': (status_desc == 'DEFINITIVO')
            }
            
            logger.info(f"RFC {rfc} - Status: {status_desc}")
            return result
            
        except Exception as e:
            logger.error(f"Error al verificar lista 69B: {str(e)}")
            return {
                'success': False,
                'message': f'Error al verificar lista 69B: {str(e)}',
                'error': str(e)
            }
    
    def probar_conexion_finkok(self) -> Dict[str, Any]:
        """
        Prueba la conexión con Finkok para validar credenciales.
        
        Returns:
            Dict con resultado de la prueba
        """
        try:
            logger.info("Probando conexión con Finkok")
            
            # Intentar inicializar el cliente
            pac = self._get_finkok_client()
            
            # Si llegamos aquí, las credenciales son válidas al menos en formato
            return {
                'success': True,
                'message': 'Conexión con Finkok configurada correctamente',
                'environment': 'Pruebas' if self.environment == Environment.TEST else 'Producción'
            }
            
        except Exception as e:
            logger.error(f"Error al probar conexión Finkok: {str(e)}")
            return {
                'success': False,
                'message': f'Error de conexión: {str(e)}',
                'error': str(e)
            }
