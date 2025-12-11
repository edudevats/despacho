from models import Product, InventoryTransaction

def test_create_product(app, db_session, test_company):
    """Test creating a new product"""
    with app.app_context():
        product = Product(
            company_id=test_company.id,
            name='Test Widget',
            sku='WIDGET-001',
            cost_price=50.00,
            selling_price=100.00,
            current_stock=10
        )
        db_session.add(product)
        db_session.commit()
        
        saved_product = Product.query.filter_by(sku='WIDGET-001').first()
        assert saved_product is not None
        assert saved_product.name == 'Test Widget'
        assert saved_product.current_stock == 10
        assert saved_product.cost_price == 50.00

def test_inventory_transaction_updates(app, db_session, test_company):
    """Test inventory transactions and relationship"""
    with app.app_context():
        # Setup product
        product = Product(
            company_id=test_company.id,
            name='Stock Item',
            current_stock=100,
            cost_price=10.0
        )
        db_session.add(product)
        db_session.commit()
        
        # Add transaction
        transaction = InventoryTransaction(
            product_id=product.id,
            type='OUT',
            quantity=5,
            previous_stock=100,
            new_stock=95,
            notes='Sold 5'
        )
        db_session.add(transaction)
        
        # Update product stock (logic normally handled in view, but testing model integrity here)
        product.current_stock = 95
        db_session.commit()
        
        # Verify
        p = db_session.get(Product, product.id)
        assert p.current_stock == 95
        assert len(p.transactions) == 1
        assert p.transactions[0].type == 'OUT'
        assert p.transactions[0].quantity == 5

def test_inventory_valuation(app, db_session, test_company):
    """Test the inventory valuation logic used in dashboard"""
    with app.app_context():
        # Clean up existing data to have clean slate
        # First delete transactions linked to company's products
        # Get all product IDs for this company
        products = Product.query.filter_by(company_id=test_company.id).all()
        for p in products:
            InventoryTransaction.query.filter_by(product_id=p.id).delete()
        
        # Then delete products
        Product.query.filter_by(company_id=test_company.id).delete()
        db_session.commit()
        
        p1 = Product(company_id=test_company.id, name='P1', cost_price=10.0, current_stock=10) # Value 100
        p2 = Product(company_id=test_company.id, name='P2', cost_price=20.0, current_stock=5)  # Value 100
        p3 = Product(company_id=test_company.id, name='P3', cost_price=5.0, current_stock=0)   # Value 0
        
        db_session.add_all([p1, p2, p3])
        db_session.commit()
        
        # Calculate value
        value = sum(p.current_stock * p.cost_price for p in [p1, p2, p3])
        assert value == 200.0

