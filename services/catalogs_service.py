"""
Servicio de Catálogos del SAT
Proporciona acceso a los catálogos de satcfdi para uso en la aplicación
"""

import satcfdi.catalogs as catalogs
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Mapeo de nombres amigables a nombres de tabla en satcfdi
CATALOG_TABLES = {
    'productos': 'C756_c_ClaveProdServ',
    'unidades': 'C756_c_ClaveUnidad',
    'uso_cfdi': 'C756_c_UsoCFDI',
    'regimen_fiscal': 'C756_c_RegimenFiscal',
    'forma_pago': 'C756_c_FormaPago',
    'metodo_pago': 'C756_c_MetodoPago',
}


class CatalogsService:
    """Servicio para consultar catálogos del SAT"""
    
    @staticmethod
    def search_catalog(catalog_name: str, search_term: str = '', limit: int = 50) -> List[Dict[str, Any]]:
        """
        Busca en un catálogo del SAT
        
        Args:
            catalog_name: Nombre del catálogo ('productos', 'unidades', etc.)
            search_term: Término de búsqueda (código o descripción)
            limit: Número máximo de resultados
            
        Returns:
            Lista de diccionarios con {code, description, metadata}
        """
        try:
            table_name = CATALOG_TABLES.get(catalog_name)
            if not table_name:
                raise ValueError(f"Catálogo desconocido: {catalog_name}")
            
            # Obtener todos los datos del catálogo
            raw_data = catalogs.select_all(table_name)
            
            results = []
            search_lower = search_term.lower().strip()
            
            for key, value in raw_data.items():
                # Extraer descripción del valor (puede ser string, tuple, dict, etc.)
                description = CatalogsService._extract_description(value)
                
                # Convertir clave a string si es necesario
                code_str = str(key)
                
                # Filtrar por término de búsqueda
                if search_lower:
                    # Buscar en código o descripción
                    if search_lower not in code_str.lower() and search_lower not in description.lower():
                        continue
                
                results.append({
                    'code': code_str,
                    'description': description,
                    'search_term': f"{code_str} {description}".lower()
                })
                
                # Limitar resultados
                if len(results) >= limit:
                    break
            
            return results
            
        except Exception as e:
            logger.error(f"Error buscando en catálogo {catalog_name}: {str(e)}")
            return []
    
    @staticmethod
    def get_catalog_item(catalog_name: str, code: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un elemento específico de un catálogo
        
        Args:
            catalog_name: Nombre del catálogo
            code: Código del elemento
            
        Returns:
            Diccionario con la información o None si no existe
        """
        try:
            table_name = CATALOG_TABLES.get(catalog_name)
            if not table_name:
                return None
            
            value = catalogs.select(table_name, code)
            if not value:
                return None
            
            description = CatalogsService._extract_description(value)
            
            return {
                'code': code,
                'description': description,
                'raw_value': str(value)
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo elemento {code} del catálogo {catalog_name}: {str(e)}")
            return None
    
    @staticmethod
    def _extract_description(value: Any) -> str:
        """
        Extrae la descripción de un valor del catálogo
        La estructura puede variar: string, tuple, list, dict
        """
        if isinstance(value, str):
            return value
        elif isinstance(value, (tuple, list)) and len(value) > 0:
            # Generalmente el primer elemento es la descripción
            return str(value[0])
        elif isinstance(value, dict):
            # Buscar key common 'descripcion', 'description', o usar el primero
            return value.get('descripcion') or value.get('description') or str(list(value.values())[0]) if value else ''
        elif hasattr(value, 'description'):
            return value.description
        else:
            return str(value)
