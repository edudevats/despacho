"""
Servicio para generar CFDIs (facturas electrónicas) válidas para timbrado con Finkok.
Utiliza la librería satcfdi para crear XMLs CFDI 4.0 de manera programática.
"""

from satcfdi.create.cfd import cfdi40
from satcfdi.models import Signer
from datetime import datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal
import logging
import os
import time
import uuid
from lxml import etree

logger = logging.getLogger(__name__)


class CFDIGenerator:
    """Generador de CFDI 4.0 para facturación electrónica"""
    
    def __init__(self, certificado_path: str, key_path: str, key_password: str):
        """
        Inicializa el generador con certificados del emisor.
        
        Args:
            certificado_path: Ruta al archivo .cer
            key_path: Ruta al archivo .key
            key_password: Contraseña de la llave privada
        """
        self.certificado_path = certificado_path
        self.key_path = key_path
        self.key_password = key_password
        self._signer = None
    
    def _get_signer(self) -> Signer:
        """Obtiene  el firmante (signer) con certificados cargados"""
        if not self._signer:
            with open(self.certificado_path, 'rb') as cer_file, \
                 open(self.key_path, 'rb') as key_file:
                self._signer = Signer.load(
                    certificate=cer_file.read(),
                    key=key_file.read(),
                    password=self.key_password
                )
        return self._signer
    
    def calcular_totales(self, conceptos: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        """
        Calcula totales de la factura basándose en los conceptos.
        
        Args:
            conceptos: Lista de conceptos/items
            
        Returns:
            Dict con subtotal, total_impuestos, total (estimados)
        """
        subtotal = Decimal('0.00')
        total_traslados = Decimal('0.00')
        total_retenciones = Decimal('0.00')
        
        for concepto in conceptos:
            cantidad = Decimal(str(concepto.get('cantidad', 1)))
            valor_unitario = Decimal(str(concepto.get('valor_unitario', 0)))
            descuento = Decimal(str(concepto.get('descuento', 0)))
            
            # Importe del concepto
            importe = (cantidad * valor_unitario) - descuento
            subtotal += importe
            
            # Calcular impuestos si aplica
            objeto_imp = concepto.get('objeto_imp', '02')
            if objeto_imp == '02':
                # Traslados (IVA)
                tipo_factor = concepto.get('tipo_factor', 'Tasa')
                if tipo_factor == 'Tasa':
                    tasa_iva = Decimal(str(concepto.get('tasa_iva', 0.16)))
                    total_traslados += (importe * tasa_iva)
                
                # Retenciones (ISR/IVA)
                # ISR
                if concepto.get('tasa_ret_isr'):
                    tasa_ret_isr = Decimal(str(concepto.get('tasa_ret_isr')))
                    total_retenciones += (importe * tasa_ret_isr)
                elif concepto.get('retencion_isr'): # Support direct amount or rate? assume rate if < 1
                     # Simplified handling
                     pass

                # IVA
                if concepto.get('tasa_ret_iva'):
                    tasa_ret_iva = Decimal(str(concepto.get('tasa_ret_iva')))
                    total_retenciones += (importe * tasa_ret_iva)

        total = subtotal + total_traslados - total_retenciones
        
        return {
            'subtotal': subtotal.quantize(Decimal('0.01')),
            'total_impuestos': (total_traslados - total_retenciones).quantize(Decimal('0.01')),
            'total': total.quantize(Decimal('0.01'))
        }
    
    def crear_factura(
        self,
        # Datos del comprobante
        serie: Optional[str] = None,
        folio: Optional[str] = None,
        fecha: Optional[datetime] = None,
        forma_pago: str = '01',  # Efectivo
        metodo_pago: str = 'PUE',  # Pago en una exhibición
        lugar_expedicion: str = '',  # Código postal
        
        # Emisor (se obtiene del certificado)
        emisor_regimen: str = '601',  # General de Ley Personas Morales
        
        # Receptor
        receptor_rfc: str = '',
        receptor_nombre: str = '',
        receptor_uso_cfdi: str = 'G03',  # Gastos en general
        receptor_regimen: str = '616',  # Sin obligaciones fiscales
        receptor_cp: str = '',
        
        # Conceptos
        conceptos: List[Dict[str, Any]] = None,
        
    ) -> tuple:
        """
        Genera un CFDI 4.0 listo para timbrar.
        
        Args:
            serie: Serie del comprobante (opcional)
            folio: Folio del comprobante (opcional)
            fecha: Fecha de emisión (default: ahora)
            forma_pago: Forma de pago código SAT
            metodo_pago: PUE o PPD
            lugar_expedicion: Código postal de expedición
            emisor_regimen: Régimen fiscal del emisor
            receptor_rfc: RFC del receptor
            receptor_nombre: Nombre del receptor
            receptor_uso_cfdi: Uso del CFDI código SAT
            receptor_regimen: Régimen fiscal del receptor
            receptor_cp: Código postal del receptor
            conceptos: Lista de conceptos/productos
            
        Returns:
            tuple: (comprobante_firmado, xml_string)
                   - comprobante_firmado: Objeto Comprobante listo para enviar a Finkok
                   - xml_string: XML serializado para guardar en archivos
            
        Example concepto:
            {
                'clave_prod_serv': '01010101',
                'cantidad': 1,
                'clave_unidad': 'E48',  # Unidad de servicio
                'descripcion': 'Servicio de consultoría',
                'valor_unitario': 1000.00,
                'descuento': 0,
                'tasa_iva': 0.16
            }
        """
        try:
            if not conceptos:
                raise ValueError("Debe proporcionar al menos un concepto")
            
            if not fecha:
                fecha = datetime.now()
            
            # Obtener firmante
            signer = self._get_signer()
            emisor_rfc = signer.rfc
            emisor_nombre = signer.legal_name or "NOMBRE EMISOR"
            
            # Calcular totales
            totales = self.calcular_totales(conceptos)
            
            # Crear lista de conceptos para CFDI
            conceptos_cfdi = []
            for idx, concepto_data in enumerate(conceptos, 1):
                cantidad = Decimal(str(concepto_data.get('cantidad', 1)))
                valor_unitario = Decimal(str(concepto_data.get('valor_unitario', 0)))
                descuento = Decimal(str(concepto_data.get('descuento', 0)))
                
                # Importe del concepto (calculado para impuestos, pero no pasado directamente al Concepto en satcfdi si se usan tipos nativos, 
                # pero pasaremos explícitos para asegurar precisión)
                importe_base_concepto = (cantidad * valor_unitario) - descuento

                # Datos de impuestos
                objeto_imp = concepto_data.get('objeto_imp', '02')
                
                # Preparar impuestos (Traslados y Retenciones)
                traslados_list = []
                retenciones_list = []
                
                if objeto_imp == '02': # Si objeto de impuesto
                    # --- TRASLADOS (IVA) ---
                    tipo_factor = concepto_data.get('tipo_factor', 'Tasa') # Tasa o Exento
                    
                    if tipo_factor == 'Tasa':
                        tasa_iva_val = concepto_data.get('tasa_iva', 0.16)
                        # SAT requires 6 decimals for TasaOCuota
                        tasa_iva = Decimal(str(tasa_iva_val)).quantize(Decimal('0.000001'))
                        importe_iva = importe_base_concepto * tasa_iva
                        
                        traslados_list.append(cfdi40.Traslado(
                            base=importe_base_concepto,
                            impuesto='002',  # IVA
                            tipo_factor='Tasa',
                            tasa_o_cuota=tasa_iva,
                            importe=importe_iva.quantize(Decimal('0.01'))
                        ))
                    elif tipo_factor == 'Exento':
                        traslados_list.append(cfdi40.Traslado(
                            base=importe_base_concepto,
                            impuesto='002', # IVA
                            tipo_factor='Exento'
                        ))
                        
                    # --- RETENCIONES (ISR/IVA) ---
                    # 1. ISR
                    if 'tasa_ret_isr' in concepto_data:
                         tasa_ret_isr_val = concepto_data.get('tasa_ret_isr')
                         # Quanitize to 6 decimals
                         tasa_ret_isr = Decimal(str(tasa_ret_isr_val)).quantize(Decimal('0.000001'))
                         
                         if tasa_ret_isr > 0:
                             importe_ret_isr = importe_base_concepto * tasa_ret_isr
                             retenciones_list.append(cfdi40.Retencion(
                                 base=importe_base_concepto,
                                 impuesto='001', # ISR
                                 tipo_factor='Tasa',
                                 tasa_o_cuota=tasa_ret_isr,
                                 importe=importe_ret_isr.quantize(Decimal('0.01'))
                             ))

                    # 2. IVA Retenido
                    if 'tasa_ret_iva' in concepto_data:
                         tasa_ret_iva_val = concepto_data.get('tasa_ret_iva')
                         tasa_ret_iva = Decimal(str(tasa_ret_iva_val)).quantize(Decimal('0.000001'))
                         
                         if tasa_ret_iva > 0:
                             importe_ret_iva = importe_base_concepto * tasa_ret_iva
                             retenciones_list.append(cfdi40.Retencion(
                                 base=importe_base_concepto,
                                 impuesto='002', # IVA
                                 tipo_factor='Tasa',
                                 tasa_o_cuota=tasa_ret_iva,
                                 importe=importe_ret_iva.quantize(Decimal('0.01'))
                             ))

                # Crear objeto Impuestos si hay traslados o retenciones
                impuestos_obj = None
                if traslados_list or retenciones_list:
                    impuestos_obj = cfdi40.Impuestos(
                        traslados=traslados_list if traslados_list else None,
                        retenciones=retenciones_list if retenciones_list else None
                    )

                # Crear objeto Concepto
                clave_prod_serv = self._sanear_clave_prod_serv(concepto_data.get('clave_prod_serv', '01010101'))
                concepto_obj = cfdi40.Concepto(
                    clave_prod_serv=clave_prod_serv,
                    no_identificacion=concepto_data.get('no_identificacion', str(idx)),
                    cantidad=cantidad,
                    clave_unidad=concepto_data.get('clave_unidad', 'E48'),
                    unidad=concepto_data.get('unidad', 'Servicio'),
                    descripcion=concepto_data.get('descripcion', 'Producto/Servicio'),
                    valor_unitario=valor_unitario,
                    descuento=descuento if descuento > 0 else None,
                    objeto_imp=objeto_imp,
                    impuestos=impuestos_obj
                )
                
                conceptos_cfdi.append(concepto_obj)
            
            # --- Global Tax Aggregation ---
            # Group Traslados by (Impuesto, TipoFactor, TasaOCuota)
            # Group Retenciones by (Impuesto)
            traslados_globales = {}  # key: (Impuesto, TipoFactor, TasaOCuota), value: {Base, Importe}
            retenciones_globales = {} # key: Impuesto, value: Importe
            
            for concepto in conceptos_cfdi:
                if not concepto.get('Impuestos'):
                    continue
                    
                c_imp = concepto['Impuestos']
                
                # Aggregate Traslados
                if c_imp.get('Traslados'):
                    for t in c_imp['Traslados']:
                        # Key for grouping
                        imp = t['Impuesto']
                        factor = t['TipoFactor']
                        tasa = t.get('TasaOCuota') # Can be None for Exento
                        key = (imp, factor, tasa)
                        
                        if key not in traslados_globales:
                            traslados_globales[key] = {'Base': Decimal('0'), 'Importe': Decimal('0')}
                        
                        traslados_globales[key]['Base'] += Decimal(str(t['Base']))
                        if t.get('Importe'):
                            traslados_globales[key]['Importe'] += Decimal(str(t['Importe']))

                # Aggregate Retenciones
                if c_imp.get('Retenciones'):
                    for r in c_imp['Retenciones']:
                        imp = r['Impuesto']
                        
                        if imp not in retenciones_globales:
                            retenciones_globales[imp] = Decimal('0')
                        
                        retenciones_globales[imp] += Decimal(str(r['Importe']))
            
            # Build Global Impuestos Object
            global_traslados_list = []
            global_retenciones_list = []
            total_trasladados = Decimal('0')
            total_retenidos = Decimal('0')
            
            for key, val in traslados_globales.items():
                imp, factor, tasa = key
                base = val['Base'].quantize(Decimal('0.01'))
                importe = val['Importe'].quantize(Decimal('0.01'))
                
                if factor != 'Exento':
                    total_trasladados += importe
                
                t_obj = cfdi40.Traslado(
                    base=base,
                    impuesto=imp,
                    tipo_factor=factor,
                    tasa_o_cuota=tasa,
                    importe=importe if factor != 'Exento' else None
                )
                global_traslados_list.append(t_obj)

            for imp, importe in retenciones_globales.items():
                importe_fmt = importe.quantize(Decimal('0.01'))
                total_retenidos += importe_fmt
                
                r_obj = cfdi40.Retencion(
                    impuesto=imp,
                    importe=importe_fmt
                )
                global_retenciones_list.append(r_obj)
            
            impuestos_globales = None
            if global_traslados_list or global_retenciones_list:
                impuestos_globales = cfdi40.Impuestos(
                    traslados=global_traslados_list if global_traslados_list else None,
                    retenciones=global_retenciones_list if global_retenciones_list else None
                )
                
                if global_traslados_list:
                    impuestos_globales['TotalImpuestosTrasladados'] = total_trasladados.quantize(Decimal('0.01'))
                
                if global_retenciones_list:
                    impuestos_globales['TotalImpuestosRetenidos'] = total_retenidos.quantize(Decimal('0.01'))

                # Note: We will inject this manually using lxml after generating the main XML object
                # because satcfdi 4.0 object assignment seems to have issues with the 'Impuestos' key mapping.
                pass
            
            # Crear emisor
            emisor = cfdi40.Emisor(
                rfc=emisor_rfc,
                nombre=emisor_nombre,
                regimen_fiscal=emisor_regimen
            )
            
            # Crear receptor
            receptor = cfdi40.Receptor(
                rfc=receptor_rfc,
                nombre=receptor_nombre,
                domicilio_fiscal_receptor=receptor_cp,
                regimen_fiscal_receptor=receptor_regimen,
                uso_cfdi=receptor_uso_cfdi
            )
            # Crear comprobante (satcfdi calcula automáticamente subtotal, total e impuestos)
            comprobante = cfdi40.Comprobante(
                serie=serie,
                folio=folio,
                fecha=fecha,
                forma_pago=forma_pago,
                metodo_pago=metodo_pago,
                tipo_de_comprobante='I',  # Ingreso
                exportacion='01',  # No aplica
                lugar_expedicion=lugar_expedicion,
                moneda='MXN',
                emisor=emisor,
                receptor=receptor,
                conceptos=conceptos_cfdi
            )
            
            # **CRÍTICO: FIRMAR EL CFDI CON EL CSD**
            # Este paso genera el Sello y agrega el Certificado al XML
            # Sin esto, Finkok rechazará con error 302 "Sello mal formado"
            comprobante.sign(signer)
            
            # Generar XML - ahora incluye Sello y Certificado
            from lxml import etree
            xml_element = comprobante.to_xml()
            
            # --- Manual Injection of Global Impuestos ---
            # SAT requires Impuestos (global) to be after Conceptos and before Complemento
            # CRITICAL: Use the SAME namespace that satcfdi uses in the root element
            if impuestos_globales:
                # Get the namespace from the root element to ensure consistency
                nsmap = xml_element.nsmap
                cfdi_ns = nsmap.get(None) or 'http://www.sat.gob.mx/cfd/4'
                
                # Create element with proper namespace (no prefix in tag, namespace in nsmap)
                imp_element = etree.Element(f"{{{cfdi_ns}}}Impuestos")
                
                # Attributes - SAT XSD order: TotalImpuestosRetenidos, TotalImpuestosTrasladados
                if global_retenciones_list:
                     imp_element.set("TotalImpuestosRetenidos", str(total_retenidos.quantize(Decimal('0.01'))))
                if global_traslados_list:
                     imp_element.set("TotalImpuestosTrasladados", str(total_trasladados.quantize(Decimal('0.01'))))
                     
                # Children - SAT XSD order: Retenciones first, then Traslados
                if impuestos_globales.get('Retenciones'):
                     retenciones_el = etree.SubElement(imp_element, f"{{{cfdi_ns}}}Retenciones")
                     for r in impuestos_globales['Retenciones']:
                         r_el = etree.SubElement(retenciones_el, f"{{{cfdi_ns}}}Retencion")
                         r_el.set("Impuesto", str(r['Impuesto']))
                         r_el.set("Importe", str(r['Importe']))

                # Children (Traslados)
                if impuestos_globales.get('Traslados'):
                     traslados_el = etree.SubElement(imp_element, f"{{{cfdi_ns}}}Traslados")
                     for t in impuestos_globales['Traslados']:
                         t_el = etree.SubElement(traslados_el, f"{{{cfdi_ns}}}Traslado")
                         # SAT XSD attribute order for Traslado
                         t_el.set("Base", str(t['Base']))
                         t_el.set("Impuesto", str(t['Impuesto']))
                         t_el.set("TipoFactor", str(t['TipoFactor']))
                         if t.get('TasaOCuota') is not None:
                             t_el.set("TasaOCuota", str(t['TasaOCuota']))
                         if t.get('Importe') is not None:
                             t_el.set("Importe", str(t['Importe']))
                
                # Insert before Complemento if exists, otherwise append
                # Standard CFDI 4.0 order: Emisor, Receptor, Conceptos, Impuestos, Complemento
                complemento = None
                for child in xml_element:
                    if child.tag.endswith('Complemento'):
                        complemento = child
                        break
                
                if complemento is not None:
                     idx = xml_element.index(complemento)
                     xml_element.insert(idx, imp_element)
                else:
                     xml_element.append(imp_element)

            # Generate XML string with proper formatting and namespace prefixes
            # IMPORTANT: Do NOT include xml_declaration=True when returning as string
            # Finkok's CFDI.from_string() cannot parse strings with XML declarations
            # The declaration should only be added when saving to file
            xml_bytes = etree.tostring(
                xml_element, 
                encoding='UTF-8', 
                xml_declaration=False,  # Must be False for string output
                pretty_print=False
            )
            xml_str = xml_bytes.decode('utf-8')
            
            logger.info(f"CFDI generado y firmado exitosamente. Total: {totales['total']}")
            
            # CRÍTICO: Convertir a objeto CFDI para Finkok
            # pac.stamp() requiere un objeto CFDI (de satcfdi.cfdi), no un Comprobante
            # Lo convertimos usando el XML que ya tenemos en memoria
            from satcfdi.cfdi import CFDI
            cfdi_obj = CFDI.from_string(xml_str)
            
            # Return both the CFDI object (for Finkok) and XML string (for saving)
            return (cfdi_obj, xml_str)
            
        except Exception as e:
            logger.error(f"Error al generar CFDI: {str(e)}")
            
            # --- CRITICAL: Save XML even if failed/unsigned for debugging ---
            try:
                # If we have a 'comprobante' object (even if partially built or unsigned)
                # we try to export it to XML to see what's wrong with the structure
                if 'comprobante' in locals() and comprobante:
                    # Generate a unique filename for the failed XML
                    timestamp = int(time.time())
                    unique_id = uuid.uuid4().hex[:8]
                    filename = f"FAILED_{timestamp}_{unique_id}.xml"
                    
                    # Get project root (go up one level from services/ to project root)
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    fallidos_dir = os.path.join(project_root, 'xml', 'fallidos')
                    os.makedirs(fallidos_dir, exist_ok=True)
                    
                    filepath = os.path.join(fallidos_dir, filename)
                    
                    # Convert to XML (without validation/signing if that's what failed)
                    # We use to_xml() which is standard in satcfdi objects
                    xml_element = comprobante.to_xml()
                    xml_bytes = etree.tostring(xml_element, encoding='UTF-8', xml_declaration=False, pretty_print=True)
                    
                    with open(filepath, 'wb') as f:
                        f.write(xml_bytes)
                        
                    logger.info(f"XML fallido guardado para debug en: {filepath}")
            except Exception as save_error:
                # Don't let the saving error mask the original error
                logger.error(f"No se pudo guardar el XML fallido: {str(save_error)}")
            
            raise
    
    def validar_datos(
        self,
        receptor_rfc: str,
        receptor_cp: str,
        receptor_regimen: str,
        receptor_uso_cfdi: str,
        lugar_expedicion: str,
        conceptos: List[Dict]
    ) -> Dict[str, Any]:
        """
        Valida los datos antes de generar CFDI.
        
        Returns:
            Dict con 'valido': bool y 'errores': List[str]
        """
        errores = []
        
        # Validar RFC
        if not receptor_rfc or len(receptor_rfc) not in [12, 13]:
            errores.append("RFC del receptor inválido")
        
        # Validar códigos postales
        if not receptor_cp or len(receptor_cp) != 5:
            errores.append("Código postal del receptor inválido")
            
        # Validar Compatibilidad Régimen vs Uso CFDI (Backend Safety Net)
        if receptor_regimen and receptor_uso_cfdi:
            if receptor_regimen == '605': # Sueldos
                es_d = receptor_uso_cfdi.startswith('D')
                if not es_d and receptor_uso_cfdi not in ['S01', 'CP01', 'CN01']:
                    errores.append("Régimen 'Sueldos y Salarios' (605) solo permite Usos D.. (Deducciones) o S01")
            
            elif receptor_regimen == '616': # Sin Obligaciones
                if receptor_uso_cfdi not in ['S01', 'CP01']:
                     errores.append("Régimen 'Sin Obligaciones' (616) solo permite Uso S01 o CP01")
            
            else:
                # Validar Morales no usen D
                es_moral = receptor_regimen in ['601', '603', '620', '622', '623', '624']
                if es_moral and receptor_uso_cfdi.startswith('D'):
                    errores.append(f"Personas Morales ({receptor_regimen}) no pueden usar Deducciones Personales (D..)")
        
        if not lugar_expedicion or len(lugar_expedicion) != 5:
            errores.append("Código postal de expedición inválido")
            
        # Validar conceptos
        if not conceptos or len(conceptos) == 0:
            errores.append("Debe haber al menos un concepto")
        
        for idx, concepto in enumerate(conceptos, 1):
            if not concepto.get('descripcion'):
                errores.append(f"Concepto {idx}: falta descripción")
            if not concepto.get('valor_unitario') or float(concepto['valor_unitario']) <= 0:
                errores.append(f"Concepto {idx}: valor unitario inválido")
            if not concepto.get('cantidad') or float(concepto['cantidad']) <= 0:
                errores.append(f"Concepto {idx}: cantidad inválida")
        
        return {
            'valido': len(errores) == 0,
            'errores': errores
        }

    def _sanear_clave_prod_serv(self, clave: Any) -> str:
        """
        Asegura que la clave sea un string de 8 dígitos con ceros a la izquierda.
        Evita el error CFDI40162.
        """
        if clave is None:
            return "01010101"
            
        if isinstance(clave, int):
            return "{:08d}".format(clave)
            
        s_clave = str(clave).strip()
        if s_clave.isdigit():
            return s_clave.zfill(8)
            
        return s_clave
