"""
Email Service
Provides email functionality using Flask-Mail.
"""

from flask import current_app, render_template_string
from flask_mail import Message
from extensions import mail


class EmailService:
    """Service for sending emails"""
    
    # Email templates
    TEMPLATES = {
        'sync_complete': """
            <h2>Sincronización Completada</h2>
            <p>Hola,</p>
            <p>La sincronización de facturas para <strong>{{ company_name }}</strong> ha finalizado.</p>
            <ul>
                <li>Facturas nuevas: {{ new_invoices }}</li>
                <li>Archivos XML guardados: {{ files_saved }}</li>
            </ul>
            <p>Saludos,<br>Sistema SAT App</p>
        """,
        'tax_reminder': """
            <h2>Recordatorio de Pago de Impuestos</h2>
            <p>Hola,</p>
            <p>Este es un recordatorio para el pago de impuestos de <strong>{{ company_name }}</strong>:</p>
            <ul>
                <li>Período: {{ month }} {{ year }}</li>
                <li>Tipo: {{ tax_type }}</li>
                <li>Monto estimado: ${{ amount | format_currency }}</li>
            </ul>
            <p>Saludos,<br>Sistema SAT App</p>
        """,
        'invoice_alert': """
            <h2>Nuevas Facturas Recibidas</h2>
            <p>Se han recibido {{ count }} nuevas facturas para <strong>{{ company_name }}</strong>.</p>
            <p>Por favor ingresa al sistema para revisarlas.</p>
        """,
        'password_reset': """
            <h2>Restablecer Contraseña</h2>
            <p>Hola {{ username }},</p>
            <p>Has solicitado restablecer tu contraseña. Haz clic en el siguiente enlace:</p>
            <p><a href="{{ reset_url }}">Restablecer contraseña</a></p>
            <p>Este enlace expira en 24 horas.</p>
            <p>Si no solicitaste este cambio, ignora este correo.</p>
        """
    }
    
    @staticmethod
    def send_email(subject, recipients, template_name=None, html_body=None, **kwargs):
        """
        Send an email.
        
        Args:
            subject: Email subject
            recipients: List of recipient email addresses
            template_name: Name of template from TEMPLATES dict
            html_body: Custom HTML body (if not using template)
            **kwargs: Template variables
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            if template_name and template_name in EmailService.TEMPLATES:
                html_body = render_template_string(
                    EmailService.TEMPLATES[template_name], 
                    **kwargs
                )
            
            if not html_body:
                current_app.logger.error("No email body provided")
                return False
            
            msg = Message(
                subject=subject,
                recipients=recipients if isinstance(recipients, list) else [recipients],
                html=html_body
            )
            
            mail.send(msg)
            current_app.logger.info(f"Email sent to {recipients}: {subject}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Error sending email: {str(e)}")
            return False
    
    @staticmethod
    def send_sync_notification(email, company_name, new_invoices, files_saved):
        """Send notification after sync completion"""
        return EmailService.send_email(
            subject=f"Sincronización completada - {company_name}",
            recipients=email,
            template_name='sync_complete',
            company_name=company_name,
            new_invoices=new_invoices,
            files_saved=files_saved
        )
    
    @staticmethod
    def send_tax_reminder(email, company_name, month, year, tax_type, amount):
        """Send tax payment reminder"""
        month_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                       'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        
        return EmailService.send_email(
            subject=f"Recordatorio: Pago de {tax_type} - {month_names[month-1]} {year}",
            recipients=email,
            template_name='tax_reminder',
            company_name=company_name,
            month=month_names[month-1],
            year=year,
            tax_type=tax_type,
            amount=amount
        )
    
    @staticmethod
    def send_invoice_alert(email, company_name, count):
        """Send alert about new invoices"""
        return EmailService.send_email(
            subject=f"Nuevas facturas recibidas - {company_name}",
            recipients=email,
            template_name='invoice_alert',
            company_name=company_name,
            count=count
        )
