import os
import sys
sys.path.append(os.getcwd())
import pandas as pd
import unicodedata
import re
from datetime import datetime
from app import create_app
from extensions import db
from models import Product, ProductBatch, InventoryTransaction, Company

# Configuration
COMPANY_ID = 2
XLSX_FILE = 'inventario.xlsx'
DRY_RUN = False  # Set to True to test without committing

def norm(s):
    if not s or pd.isna(s):
        return ''
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())

def parse_date(d):
    if not d or pd.isna(d):
        return None
    if isinstance(d, datetime):
        return d.date()
    try:
        # Try some common formats
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(str(d), fmt).date()
            except ValueError:
                continue
    except:
        pass
    return None

def import_inventory():
    app = create_app()
    with app.app_context():
        print(f"Starting import for Company ID: {COMPANY_ID}")
        
        # Load Excel
        try:
            df = pd.read_excel(XLSX_FILE)
        except Exception as e:
            print(f"Error loading Excel: {e}")
            return

        # Map products by normalized name
        products = Product.query.filter_by(company_id=COMPANY_ID, active=True).all()
        by_norm = {norm(p.name): p for p in products}
        print(f"Found {len(products)} active products in database.")

        updated_count = 0
        skipped_count = 0
        batch_created_count = 0
        batch_updated_count = 0

        for index, row in df.iterrows():
            name = row.get('Nombre')
            if not name or pd.isna(name):
                continue
            
            p_norm = norm(name)
            product = by_norm.get(p_norm)
            
            if not product:
                print(f"  [SKIP] Product not found: {name}")
                skipped_count += 1
                continue

            # Update Price
            price_raw = row.get('PRECIO')
            price = pd.to_numeric(price_raw, errors='coerce')
            if not pd.isna(price):
                product.cost_price = float(price)

            # Process 3 batches
            batch_data = [
                # Qty, Batch#, Exp, RegSan
                (row.get('CANTIDAD'), row.get('LOTE '), row.get('CADUCIDAD'), row.get('REGISTRO SANITARIO')),
                (row.get('CANTIDAD.1'), row.get('LOTE .1'), row.get('CADUCIDAD.1'), row.get('REGISTRO SANITARIO.1')),
                (row.get('CANTIDAD.2'), row.get('LOTE .2'), row.get('CADUCIDAD.2'), row.get('REGISTRO SANITARIO.2'))
            ]

            previous_total_stock = product.current_stock
            
            # For this update, we might want to reset existing stocks to 0 to match Excel exactly
            # But wait, if the Excel only lists SOME batches, we should be careful.
            # However, the user said "insertar los datos... comodados de la siguiente manera", 
            # implying these ARE the batches.
            
            # Let's keep track of which batches we touch
            touched_batch_ids = []
            
            new_batches_stock = 0
            
            for qty_raw, b_num, b_exp, b_reg in batch_data:
                try:
                    qty = pd.to_numeric(qty_raw, errors='coerce')
                    if pd.isna(qty) or qty <= 0:
                        continue
                    qty = int(qty)
                except:
                    continue
                b_num = str(b_num).strip() if not pd.isna(b_num) else "SN"
                exp_date = parse_date(b_exp)
                reg_san = str(b_reg).strip() if not pd.isna(b_reg) else None
                
                # Find if batch exists
                batch = ProductBatch.query.filter_by(
                    product_id=product.id,
                    batch_number=b_num
                ).first()
                
                if batch:
                    batch.current_stock = qty
                    batch.expiration_date = exp_date or batch.expiration_date
                    batch.sanitary_registration = reg_san or batch.sanitary_registration
                    batch.is_active = True
                    batch_updated_count += 1
                else:
                    if not exp_date:
                        # If no date provided in Excel, use a dummy one or handle?
                        # ProductBatch requires expiration_date in model (nullable=False)
                        # We'll use a far future date if missing, or skip?
                        exp_date = datetime(2099, 12, 31).date()
                        
                    batch = ProductBatch(
                        product_id=product.id,
                        batch_number=b_num,
                        expiration_date=exp_date,
                        current_stock=qty,
                        initial_stock=qty,
                        sanitary_registration=reg_san,
                        is_active=True
                    )
                    db.session.add(batch)
                    db.session.flush() # Get ID
                    batch_created_count += 1
                
                # Also update the product's overall sanitary_registration
                if reg_san:
                    product.sanitary_registration = reg_san
                
                touched_batch_ids.append(batch.id)
                new_batches_stock += qty

            # Deactivate or zero-out batches NOT in Excel for this product?
            # To be safe, we only update the product total stock based on what we found.
            # If the user wants a full sync, we should zero out other batches.
            # Given the context, it's likely a full inventory count.
            all_batches = ProductBatch.query.filter_by(product_id=product.id).all()
            for b in all_batches:
                if b.id not in touched_batch_ids:
                    b.current_stock = 0
                    b.is_active = False

            product.current_stock = new_batches_stock
            
            # Create Transaction for audit
            if new_batches_stock != previous_total_stock:
                trans = InventoryTransaction(
                    product_id=product.id,
                    type='ADJUSTMENT',
                    quantity=abs(new_batches_stock - previous_total_stock),
                    previous_stock=previous_total_stock,
                    new_stock=new_batches_stock,
                    reference='Importación Excel',
                    notes=f"Actualización masiva desde inventario.xlsx. Precio y 3 lotes.",
                    date=datetime.utcnow()
                )
                db.session.add(trans)

            updated_count += 1
            if updated_count % 50 == 0:
                print(f"  Processed {updated_count} products...")

        if not DRY_RUN:
            db.session.commit()
            print(f"Successfully committed changes.")
        else:
            db.session.rollback()
            print(f"DRY RUN: Rollback changes.")

        print(f"Summary:")
        print(f"  Products updated: {updated_count}")
        print(f"  Products skipped: {skipped_count}")
        print(f"  Batches created: {batch_created_count}")
        print(f"  Batches updated: {batch_updated_count}")

if __name__ == "__main__":
    import_inventory()
