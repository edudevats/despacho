import ast
import os

with open('temp_app.py', 'r', encoding='utf-8') as f:
    source = f.read()
    lines = source.split('\n')

class NodeVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions = []
        
    def visit_FunctionDef(self, node):
        self.functions.append({
            'name': node.name,
            'start_line': node.lineno,
            'end_line': node.end_lineno,
            'decorator_list': [d for d in node.decorator_list]
        })
        self.generic_visit(node)

tree = ast.parse(source)
visitor = NodeVisitor()
visitor.visit(tree)

def extract_node(func_name):
    for f in visitor.functions:
        if f['name'] == func_name:
            start = f['start_line']
            if f['decorator_list']:
                start = min(d.lineno for d in f['decorator_list'])
            
            text = '\n'.join(lines[start-1:f['end_line']]) + '\n'
            if '@app.route' in text:
                return text
            return ""
    return ""

print("Found", len(visitor.functions), "functions")

blueprints = {
    'auth': ['login', 'logout', 'change_password'],
    'admin': ['admin_users', 'admin_add_user', 'admin_edit_user', 'admin_delete_user'],
    'main': ['index'],
    'companies': ['companies', 'add_company', 'delete_company', 'edit_company', 'sync_company', 'csf_company', 'search_invoices', 'company_qr', 'company_qr_download', 'invoice_qr', 'api_company_stats'],
    'movements': ['movements_list', 'company_movements', 'categories_list', 'suppliers_list', 'advanced_search', 'taxes_dashboard', 'company_suppliers', 'company_supplier_detail', 'company_categories', 'create_category', 'edit_category', 'record_tax_payment'],
    'invoicing': ['facturacion_list', 'facturacion_dashboard', 'facturacion_credenciales', 'facturacion_download_timbrado', 'facturacion_invoice_pdf', 'facturacion_estado', 'facturacion_lista69b', 'facturacion_actualizar_estado_db', 'crear_factura', 'facturacion_cancelar', 'company_ppd', 'acreditar_ppd', 'desacreditar_ppd', 'sales_list', 'sales_dashboard', 'invoice_detail', 'download_invoice'],
    'api': ['api_search_customers', 'api_get_customer', 'api_search_products', 'api_template_items', 'api_catalog_search', 'api_catalog_get'],
}

ignore_funcs = {'create_app', 'format_currency', 'chunk_split', 'load_user', 'handle_csrf_error', 'admin_required', 'inject_inventory_admin_helper', 'inventory_admin_required', 'require_company_perm'}

def process_route_text(text, bp_name):
    # Replace @app.route with @bp_name.route
    text = text.replace('@app.route', f'@{bp_name}_bp.route')
    # Unindent everything 4 spaces because they were inside create_app
    processed_lines = []
    for line in text.split('\n'):
        if line.startswith('    '):
            processed_lines.append(line[4:])
        else:
            processed_lines.append(line)
    return '\n'.join(processed_lines)

os.makedirs('routes', exist_ok=True)

imports = """import os
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, limiter, cache, mail, csrf, migrate
from sqlalchemy import func, extract
from datetime import datetime, timedelta, timezone
from utils.timezone_helper import now_mexico, to_mexico_time
from utils.helpers import safe_redirect_target, find_company_invoice_xml_path, parse_invoice_xml_for_db, get_or_create_supplier, update_supplier_stats
from utils.decorators import admin_required, inventory_admin_required, require_company_perm
from models import *
from forms import *
from services.sat_service import SATService, SATError
from services.qr_service import QRService

logger = logging.getLogger(__name__)

"""

bp_files = {bp: imports + f"\n{bp}_bp = Blueprint('{bp}', __name__)\n\n" for bp in blueprints.keys()}
bp_files['inventory'] = imports + "\ninventory_bp = Blueprint('inventory', __name__)\n\n"

for f in visitor.functions:
    name = f['name']
    if name in ignore_funcs:
        continue
    
    bp_name = 'inventory'
    for bp, funcs in blueprints.items():
        if name in funcs:
            bp_name = bp
            break
            
    text = extract_node(name)
    if not text:
        continue
        
    text = process_route_text(text, bp_name)
    bp_files[bp_name] += text + '\n'

for bp, content in bp_files.items():
    with open(f'routes/{bp}.py', 'w', encoding='utf-8') as f:
        f.write(content)
