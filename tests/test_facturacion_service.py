import pytest
from unittest.mock import MagicMock, patch
from services.facturacion_service import FacturacionService
from satcfdi.pacs import CancelReason

@pytest.fixture
def mock_signer():
    return MagicMock()

@pytest.fixture
def facturacion_service(mock_signer):
    service = FacturacionService(
        finkok_username="test_user",
        finkok_password="test_password",
        environment="TEST",
        signer=mock_signer
    )
    return service

@patch('services.facturacion_service.CFDI')
def test_cancelar_factura_motivo_02_exito(mock_cfdi_class, facturacion_service):
    # Setup
    mock_pac = MagicMock()
    mock_acuse = MagicMock()
    mock_acuse.xml = b"<Acuse>Cancelado</Acuse>"
    mock_pac.cancel.return_value = mock_acuse
    
    facturacion_service._finkok_client = mock_pac
    mock_cfdi_instance = MagicMock()
    mock_cfdi_class.from_string.return_value = mock_cfdi_instance
    
    # Execute
    resultado = facturacion_service.cancelar_factura(
        cfdi_xml="<cfdi:Comprobante></cfdi:Comprobante>",
        reason="02"
    )
    
    # Assert
    assert resultado['success'] is True
    assert resultado['acuse'] == "<Acuse>Cancelado</Acuse>"
    mock_pac.cancel.assert_called_once_with(
        cfdi=mock_cfdi_instance,
        reason=CancelReason.COMPROBANTE_EMITIDO_CON_ERRORES_SIN_RELACION,
        substitution_id=None,
        signer=facturacion_service.signer
    )

@patch('services.facturacion_service.CFDI')
def test_cancelar_factura_motivo_01_exito(mock_cfdi_class, facturacion_service):
    # Setup
    mock_pac = MagicMock()
    mock_acuse = MagicMock()
    mock_acuse.xml = b"<Acuse>Cancelado</Acuse>"
    mock_pac.cancel.return_value = mock_acuse
    
    facturacion_service._finkok_client = mock_pac
    mock_cfdi_instance = MagicMock()
    mock_cfdi_class.from_string.return_value = mock_cfdi_instance
    
    # Execute
    resultado = facturacion_service.cancelar_factura(
        cfdi_xml="<cfdi:Comprobante></cfdi:Comprobante>",
        reason="01",
        substitution_uuid="1234-5678-9012-3456"
    )
    
    # Assert
    assert resultado['success'] is True
    mock_pac.cancel.assert_called_once_with(
        cfdi=mock_cfdi_instance,
        reason=CancelReason.COMPROBANTE_EMITIDO_CON_ERRORES_CON_RELACION,
        substitution_id="1234-5678-9012-3456",
        signer=facturacion_service.signer
    )

def test_cancelar_factura_motivo_01_sin_sustitucion(facturacion_service):
    # Execute
    resultado = facturacion_service.cancelar_factura(
        cfdi_xml="<cfdi:Comprobante></cfdi:Comprobante>",
        reason="01"
    )
    
    # Assert
    assert resultado['success'] is False
    assert "requiere el UUID de sustitución" in resultado['message']

def test_cancelar_factura_motivo_invalido(facturacion_service):
    # Execute
    resultado = facturacion_service.cancelar_factura(
        cfdi_xml="<cfdi:Comprobante></cfdi:Comprobante>",
        reason="99"
    )
    
    # Assert
    assert resultado['success'] is False
    assert "Motivo de cancelación inválido" in resultado['message']

def test_cancelar_factura_sin_signer():
    # Setup
    service = FacturacionService(
        finkok_username="test",
        finkok_password="test",
        signer=None
    )
    
    # Execute
    resultado = service.cancelar_factura(
        cfdi_xml="<cfdi:Comprobante></cfdi:Comprobante>",
        reason="02"
    )
    
    # Assert
    assert resultado['success'] is False
    assert "FIEL (Signer) no configurado" in resultado['message']
