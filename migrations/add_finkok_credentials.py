"""
Script de migración para agregar la tabla finkok_credentials
"""

if __name__ == '__main__':
    import sys
    import os
    
    # Add parent directory to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from app import create_app
    from extensions import db
    
    app = create_app()
    
    with app.app_context():
        # Import model to ensure table is registered
        from models import FinkokCredentials
        
        # Create table
        db.create_all()
        print("✓ Tabla finkok_credentials creada exitosamente")
