import sys
import os
import traceback

# Add project root to path
sys.path.append(os.getcwd())

from utils.timezone_helper import now_mexico

print("Importing forms...")
try:
    from forms import CFDIComprobanteForm
    print("Forms imported successfully.")
except ImportError:
    print("Failed to import forms. Traceback:")
    traceback.print_exc()
    sys.exit(1)
except Exception:
    print("Error during import:")
    traceback.print_exc()
    sys.exit(1)

def verify():
    print("Verifying CFDIComprobanteForm defaults...")
    try:
        # Inspect the field directly on the class to avoid instantiation issues if app context is missing
        # WTForms fields are UnboundField on the class
        fecha_field = CFDIComprobanteForm.fecha
        
        # In newer WTForms, 'default' might be in kwargs or args of UnboundField
        # But easier to just check if we can instantiate it, or check the args
        
        print(f"Field args: {fecha_field.args}")
        print(f"Field kwargs: {fecha_field.kwargs}")
        
        default_val = fecha_field.kwargs.get('default')
        print(f"Default value found: {default_val}")
        
        if default_val == now_mexico:
             print("\n✅ SUCCESS: 'default' is set to 'now_mexico' function.")
        else:
             print(f"\n❌ FAILURE: 'default' is {default_val}, expected {now_mexico}")
             
    except Exception as e:
        print(f"Verification failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    verify()
