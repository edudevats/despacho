"""
Application Tests
Basic tests for the SAT application.
"""

import pytest


class TestAppBasics:
    """Test basic application functionality"""
    
    def test_app_exists(self, app):
        """Test application is created"""
        assert app is not None
    
    def test_app_is_testing(self, app):
        """Test app is in testing mode"""
        assert app.config['TESTING'] is True
    
    def test_csrf_disabled_in_testing(self, app):
        """Test CSRF is disabled in testing"""
        assert app.config['WTF_CSRF_ENABLED'] is False


class TestRoutes:
    """Test application routes"""
    
    def test_login_page_loads(self, client):
        """Test login page is accessible"""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'login' in response.data.lower() or b'usuario' in response.data.lower()
    
    def test_index_requires_login(self, client):
        """Test index redirects to login when not authenticated"""
        response = client.get('/')
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_companies_requires_login(self, client):
        """Test companies page requires authentication"""
        response = client.get('/companies')
        assert response.status_code == 302
        assert '/login' in response.location


class TestAuthentication:
    """Test authentication functionality"""
    
    def test_login_with_valid_credentials(self, client, test_user, app):
        """Test login with valid credentials"""
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'testpassword123'
        }, follow_redirects=True)
        assert response.status_code == 200
    
    def test_login_with_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        response = client.post('/login', data={
            'username': 'wronguser',
            'password': 'wrongpassword'
        })
        assert response.status_code == 200
        # Should stay on login page
    
    def test_logout(self, authenticated_client):
        """Test logout functionality"""
        response = authenticated_client.get('/logout', follow_redirects=True)
        assert response.status_code == 200


class TestCompanies:
    """Test company functionality"""
    
    def test_authenticated_user_can_view_companies(self, authenticated_client):
        """Test authenticated user can access companies page"""
        response = authenticated_client.get('/companies')
        assert response.status_code == 200
    
    def test_add_company(self, authenticated_client, app):
        """Test adding a new company"""
        response = authenticated_client.post('/companies/add', data={
            'rfc': 'XAXX010101000',
            'name': 'Test Company S.A.'
        }, follow_redirects=True)
        assert response.status_code == 200


class TestModels:
    """Test database models"""
    
    def test_user_creation(self, app, db_session):
        """Test user model creation"""
        from models import User
        from werkzeug.security import generate_password_hash
        
        user = User(
            username='newuser',
            password_hash=generate_password_hash('password123')
        )
        db_session.add(user)
        db_session.commit()
        
        assert user.id is not None
        assert user.username == 'newuser'
    
    def test_company_creation(self, app, db_session):
        """Test company model creation"""
        from models import Company
        
        company = Company(
            rfc='TEST654321XYZ',
            name='Company Test'
        )
        db_session.add(company)
        db_session.commit()
        
        assert company.id is not None
        assert company.rfc == 'TEST654321XYZ'


class TestServices:
    """Test service modules"""
    
    def test_qr_service_generates_code(self, app):
        """Test QR service generates valid QR code"""
        from services.qr_service import QRService
        
        with app.app_context():
            qr_base64 = QRService.generate_qr_base64("Test data")
            assert qr_base64.startswith("data:image/png;base64,")
    
    def test_qr_service_cfdi_format(self, app, sample_invoice_data):
        """Test QR service generates CFDI format QR"""
        from services.qr_service import QRService
        
        with app.app_context():
            qr = QRService.generate_cfdi_qr(
                uuid=sample_invoice_data['uuid'],
                issuer_rfc=sample_invoice_data['issuer_rfc'],
                receiver_rfc=sample_invoice_data['receiver_rfc'],
                total=sample_invoice_data['total'],
                seal_last_8="ABCD1234"
            )
            assert qr.startswith("data:image/png;base64,")
