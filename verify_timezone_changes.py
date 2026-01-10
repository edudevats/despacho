import sys
import os
from datetime import datetime
import pytz

# Add project root to path
sys.path.append(os.getcwd())

from app import create_app
from forms import CFDIComprobanteForm, BatchForm
from utils.timezone_helper import now_mexico

def verify_forms():
    app = create_app()
    with app.app_context():
        # Instantiate forms
        cfdi_form = CFDIComprobanteForm()
        batch_form = BatchForm()
        
        # Get default values
        cfdi_date = cfdi_form.fecha.default() if callable(cfdi_form.fecha.default) else cfdi_form.fecha.default
        batch_date = batch_form.acquisition_date.default() if callable(batch_form.acquisition_date.default) else batch_form.acquisition_date
        
        # Verify CFDI form date
        print(f"CFDI Form Date (Default): {cfdi_date}")
        print(f"CFDI Form Date TZ: {cfdi_date.tzinfo}")
        
        # Verify Batch form date
        print(f"Batch Form Date (Default): {batch_date}")
        
        # Current Mexico time for comparison
        current_mx = now_mexico()
        print(f"Current Mexico Time: {current_mx}")
        
        # Allow small delta for execution time
        time_diff = abs((current_mx - cfdi_date).total_seconds())
        
        if time_diff < 5 and str(cfdi_date.tzinfo) == "America/Mexico_City":
            print("\n✅ CFDI Form uses Mexico City time correctly.")
        else:
            print(f"\n❌ CFDI Form time mismatch or wrong timezone! Diff: {time_diff}s, TZ: {cfdi_date.tzinfo}")

        if cfdi_date.date() == batch_date: # BatchForm uses DateField, likely returns date object
             print("✅ Batch Form date matches.")
        else:
             print(f"⚠️ Batch Form date check: {batch_date} vs {cfdi_date.date()}")

if __name__ == "__main__":
    verify_forms()
