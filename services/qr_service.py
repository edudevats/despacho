"""
QR Code Service
Generate QR codes for invoices and other data.
"""

import io
import base64
import qrcode
from qrcode.image.pil import PilImage
from flask import current_app


class QRService:
    """Service for generating QR codes"""
    
    @staticmethod
    def generate_qr(data, size=10, border=4):
        """
        Generate a QR code image.
        
        Args:
            data: String data to encode
            size: Box size (default 10)
            border: Border size (default 4)
        
        Returns:
            PIL Image object
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        return img
    
    @staticmethod
    def generate_qr_base64(data, size=10, border=4):
        """
        Generate a QR code and return as base64 string.
        
        Args:
            data: String data to encode
            size: Box size
            border: Border size
        
        Returns:
            Base64 encoded PNG string
        """
        img = QRService.generate_qr(data, size, border)
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"
    
    @staticmethod
    def generate_qr_bytes(data, size=10, border=4):
        """
        Generate a QR code and return as bytes.
        
        Args:
            data: String data to encode
            size: Box size
            border: Border size
        
        Returns:
            PNG image bytes
        """
        img = QRService.generate_qr(data, size, border)
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return buffer.getvalue()
    
    @staticmethod
    def generate_cfdi_qr(uuid, issuer_rfc, receiver_rfc, total, seal_last_8):
        """
        Generate QR code for CFDI invoice following SAT specifications.
        
        Args:
            uuid: Invoice UUID
            issuer_rfc: Issuer RFC
            receiver_rfc: Receiver RFC  
            total: Invoice total
            seal_last_8: Last 8 characters of digital seal
        
        Returns:
            Base64 encoded PNG string
        """
        # SAT verification URL format
        url = (
            f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?"
            f"id={uuid}&"
            f"re={issuer_rfc}&"
            f"rr={receiver_rfc}&"
            f"tt={total:.6f}&"
            f"fe={seal_last_8}"
        )
        
        return QRService.generate_qr_base64(url, size=8, border=2)
    
    @staticmethod
    def generate_company_qr(company):
        """
        Generate QR code with company information.
        
        Args:
            company: Company model instance
        
        Returns:
            Base64 encoded PNG string
        """
        data = f"RFC: {company.rfc}\nNombre: {company.name}"
        return QRService.generate_qr_base64(data)
    
    @staticmethod
    def generate_vcard_qr(name, rfc, email=None, phone=None):
        """
        Generate QR code with vCard format.
        
        Args:
            name: Contact name
            rfc: RFC number
            email: Email address
            phone: Phone number
        
        Returns:
            Base64 encoded PNG string
        """
        vcard = f"""BEGIN:VCARD
VERSION:3.0
N:{name}
ORG:{name}
NOTE:RFC: {rfc}"""
        
        if email:
            vcard += f"\nEMAIL:{email}"
        if phone:
            vcard += f"\nTEL:{phone}"
        
        vcard += "\nEND:VCARD"
        
        return QRService.generate_qr_base64(vcard)
