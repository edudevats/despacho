"""
Pytest Configuration and Fixtures
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope='module')
def app():
    """Create application for testing"""
    from config import TestingConfig
    from app import create_app
    from extensions import db
    
    test_app = create_app(TestingConfig)
    
    with test_app.app_context():
        db.create_all()
    
    yield test_app
    
    with test_app.app_context():
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """Create CLI test runner"""
    return app.test_cli_runner()


@pytest.fixture(scope='function')
def db_session(app):
    """Create database session for testing"""
    from extensions import db
    
    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture(scope='function')
def test_user(app):
    """Create a test user"""
    from extensions import db
    from models import User
    from werkzeug.security import generate_password_hash
    
    with app.app_context():
        # Check if test user already exists
        existing = User.query.filter_by(username='testuser').first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
        
        user = User(
            username='testuser',
            password_hash=generate_password_hash('testpassword123')
        )
        db.session.add(user)
        db.session.commit()
        
        user_id = user.id
        
        yield user
        
        # Cleanup
        user_to_delete = db.session.get(User, user_id)
        if user_to_delete:
            db.session.delete(user_to_delete)
            db.session.commit()


@pytest.fixture(scope='function')
def test_company(app):
    """Create a test company"""
    from extensions import db
    from models import Company, Product, InventoryTransaction, Invoice, Movement, Supplier, Category, TaxPayment
    
    with app.app_context():
        # Check if test company already exists
        existing = Company.query.filter_by(rfc='TEST123456ABC').first()
        if existing:
            # Clean up dependencies for existing company to allow delete
            
            # Inventory
            products = Product.query.filter_by(company_id=existing.id).all()
            for p in products:
                InventoryTransaction.query.filter_by(product_id=p.id).delete()
            Product.query.filter_by(company_id=existing.id).delete()
            
            # Other dependencies (simplified from app.py logic)
            Movement.query.filter_by(company_id=existing.id).delete()
            Invoice.query.filter_by(company_id=existing.id).delete()
            Supplier.query.filter_by(company_id=existing.id).delete()
            Category.query.filter_by(company_id=existing.id).delete()
            TaxPayment.query.filter_by(company_id=existing.id).delete()
            
            db.session.delete(existing)
            db.session.commit()
        
        company = Company(
            rfc='TEST123456ABC',
            name='Empresa de Prueba S.A. de C.V.'
        )
        db.session.add(company)
        db.session.commit()
        
        company_id = company.id
        
        yield company
        
        # Cleanup
        company_to_delete = db.session.get(Company, company_id)
        if company_to_delete:
            # Inventory
            products = Product.query.filter_by(company_id=company_to_delete.id).all()
            for p in products:
                InventoryTransaction.query.filter_by(product_id=p.id).delete()
            Product.query.filter_by(company_id=company_to_delete.id).delete()
            
            # Other dependencies
            Movement.query.filter_by(company_id=company_to_delete.id).delete()
            Invoice.query.filter_by(company_id=company_to_delete.id).delete()
            Supplier.query.filter_by(company_id=company_to_delete.id).delete()
            Category.query.filter_by(company_id=company_to_delete.id).delete()
            TaxPayment.query.filter_by(company_id=company_to_delete.id).delete()
            
            db.session.delete(company_to_delete)
            db.session.commit()


@pytest.fixture(scope='function')
def authenticated_client(client, test_user, app):
    """Create authenticated test client"""
    with client.session_transaction() as session:
        session['_user_id'] = str(test_user.id)
        session['_fresh'] = True
    
    return client


@pytest.fixture
def sample_invoice_data():
    """Sample invoice data for testing"""
    return {
        'uuid': 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE',
        'date': '2024-01-15',
        'total': 1160.00,
        'subtotal': 1000.00,
        'tax': 160.00,
        'type': 'I',
        'issuer_rfc': 'XAXX010101000',
        'issuer_name': 'Emisor Prueba',
        'receiver_rfc': 'XEXX010101000',
        'receiver_name': 'Receptor Prueba',
        'forma_pago': '03',
        'metodo_pago': 'PUE',
        'uso_cfdi': 'G03'
    }
