import os
import re

blueprints = {
    'auth': ['login', 'logout', 'change_password'],
    'admin': ['admin_users', 'admin_add_user', 'admin_edit_user', 'admin_delete_user'],
    'main': ['index'],
    'companies': ['companies', 'add_company', 'delete_company', 'edit_company', 'sync_company', 'csf_company', 'search_invoices', 'company_qr', 'company_qr_download', 'invoice_qr', 'api_company_stats'],
    'movements': ['movements_list', 'company_movements', 'categories_list', 'suppliers_list', 'advanced_search', 'taxes_dashboard', 'company_suppliers', 'company_supplier_detail', 'company_categories', 'create_category', 'edit_category', 'record_tax_payment'],
    'invoicing': ['facturacion_list', 'facturacion_dashboard', 'facturacion_credenciales', 'facturacion_download_timbrado', 'facturacion_invoice_pdf', 'facturacion_estado', 'facturacion_lista69b', 'facturacion_actualizar_estado_db', 'crear_factura', 'facturacion_cancelar', 'company_ppd', 'acreditar_ppd', 'desacreditar_ppd', 'sales_list', 'sales_dashboard', 'invoice_detail', 'download_invoice'],
    'api': ['api_search_customers', 'api_get_customer', 'api_search_products', 'api_template_items', 'api_catalog_search', 'api_catalog_get'],
}

ignore_list = ['static']

func_to_bp = {}
for bp, funcs in blueprints.items():
    for f in funcs:
        func_to_bp[f] = bp

routes_dir = 'routes'
for root, dirs, files in os.walk(routes_dir):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            def repl(match):
                func_name = match.group(1)
                
                # If already namespaced (e.g., auth.login), skip
                if '.' in func_name:
                    return match.group(0)
                    
                if func_name in ignore_list:
                    return match.group(0)
                    
                bp = func_to_bp.get(func_name, 'inventory')
                return f"url_for('{bp}.{func_name}'"

            new_content = re.sub(r"url_for\(\s*['\"]([^'\"]+)['\"]", repl, content)

            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {filepath}")

print("Python routes update completed!")
