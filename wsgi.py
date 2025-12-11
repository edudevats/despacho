"""
WSGI entry point for the SAT Invoice Management application.

This file is used by WSGI servers (like Gunicorn, uWSGI, or mod_wsgi)
to serve the Flask application in production.

Usage examples:
    Gunicorn: gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
    uWSGI: uwsgi --http :8000 --wsgi-file wsgi.py --callable app
    
For PythonAnywhere:
    - Set the WSGI configuration file path to this file
    - Use the 'application' variable as the WSGI callable
"""

import sys
import os

# Add your project directory to the sys.path
# For PythonAnywhere, adjust this path to match your project location
project_home = '/home/edudracos/despacho'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from app import create_app
from config import Config

# Create the Flask application instance
# Use the Config class, not a string
app = create_app(Config)

# PythonAnywhere expects the variable to be called 'application'
application = app

if __name__ == "__main__":
    # This allows running the app directly with: python wsgi.py
    # However, in production, you should use a proper WSGI server
    app.run()
