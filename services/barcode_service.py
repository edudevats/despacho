"""
Barcode Lookup Service - Hybrid approach

This service provides barcode lookup functionality using external APIs
(UPCitemdb, EAN-Search, etc.) as a fallback when products aren't in the local catalog.

The service allows automatic product discovery while maintaining local control.
"""

import requests
import logging
from typing import Optional, Dict, Any
from config import Config

logger = logging.getLogger(__name__)


class BarcodeAPIService:
    """
    Service for looking up product information via barcode using external APIs.
    
    Supports multiple API providers:
    - UPCitemdb (recommended, has free tier)
    - EAN-Search
    - Barcode Lookup API
    """
    
    def __init__(self):
        self.api_provider = Config.BARCODE_API_PROVIDER or 'upcitemdb'
        self.api_key = Config.BARCODE_API_KEY
        self.api_url = Config.BARCODE_API_URL
        
    def lookup(self, barcode: str) -> Optional[Dict[str, Any]]:
        """
        Look up a barcode in the external API.
        
        Args:
            barcode: The barcode number (EAN, UPC, etc.)
            
        Returns:
            Dict with product information if found, None otherwise
        """
        if not self.api_url or not self.api_key:
            logger.warning("Barcode API not configured. Skipping external lookup.")
            return None
            
        try:
            if self.api_provider == 'upcitemdb':
                return self._lookup_upcitemdb(barcode)
            elif self.api_provider == 'ean-search':
                return self._lookup_ean_search(barcode)
            else:
                logger.error(f"Unknown barcode API provider: {self.api_provider}")
                return None
        except Exception as e:
            logger.error(f"Error during barcode lookup for {barcode}: {str(e)}")
            return None
    
    def _lookup_upcitemdb(self, barcode: str) -> Optional[Dict[str, Any]]:
        """
        Lookup barcode using UPCitemdb API.
        
        API endpoint: https://api.upcitemdb.com/prod/trial/lookup
        Free tier: 100 requests per day
        """
        try:
            headers = {
                'accept': 'application/json',
                'user_key': self.api_key,
            }
            
            params = {'upc': barcode}
            
            response = requests.get(
                self.api_url,
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # UPCitemdb returns items array
                if data.get('items') and len(data['items']) > 0:
                    item = data['items'][0]
                    return self._normalize_upcitemdb_response(item)
                else:
                    logger.info(f"Barcode {barcode} not found in UPCitemdb")
                    return None
                    
            elif response.status_code == 404:
                logger.info(f"Barcode {barcode} not found in UPCitemdb")
                return None
            else:
                logger.error(
                    f"UPCitemdb API error: {response.status_code} - {response.text}"
                )
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during UPCitemdb lookup: {str(e)}")
            return None
    
    def _lookup_ean_search(self, barcode: str) -> Optional[Dict[str, Any]]:
        """
        Lookup barcode using EAN-Search API.
        
        API endpoint: https://api.ean-search.org/api
        """
        try:
            params = {
                'token': self.api_key,
                'op': 'barcode-lookup',
                'ean': barcode,
                'format': 'json',
            }
            
            response = requests.get(
                self.api_url,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if product was found
                if data.get('product'):
                    return self._normalize_ean_search_response(data)
                else:
                    logger.info(f"Barcode {barcode} not found in EAN-Search")
                    return None
            else:
                logger.error(
                    f"EAN-Search API error: {response.status_code} - {response.text}"
                )
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during EAN-Search lookup: {str(e)}")
            return None
    
    def _normalize_upcitemdb_response(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize UPCitemdb response to our standard format.
        """
        return {
            'barcode': item.get('ean'),
            'name': item.get('title', ''),
            'description': item.get('description', ''),
            'brand': item.get('brand', ''),
            'manufacturer': item.get('manufacturer', ''),
            'category': item.get('category', ''),
            'images': item.get('images', []),
            'source': 'upcitemdb',
        }
    
    def _normalize_ean_search_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize EAN-Search response to our standard format.
        """
        return {
            'barcode': data.get('ean'),
            'name': data.get('product', {}).get('name', ''),
            'description': '',
            'brand': data.get('product', {}).get('brand', ''),
            'manufacturer': data.get('product', {}).get('manufacturer', ''),
            'category': data.get('product', {}).get('category', ''),
            'images': [],
            'source': 'ean-search',
        }


# Singleton instance
_barcode_service = None


def get_barcode_service() -> BarcodeAPIService:
    """Get or create the barcode service instance."""
    global _barcode_service
    if _barcode_service is None:
        _barcode_service = BarcodeAPIService()
    return _barcode_service
