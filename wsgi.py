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
from dotenv import load_dotenv

# Add your project directory to the sys.path
# For PythonAnywhere, this should be the absolute path to your project
project_home = '/home/edudracos/despacho'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Explicitly load environment variables from .env file in project root ONLY
# This ensures FERNET_KEY and other env vars are available before app initialization
env_path = os.path.join(project_home, '.env')

# Load .env file - dotenv_path ensures it loads ONLY from this specific file
# override=False means existing environment variables take precedence
# verbose=False to avoid unnecessary output
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path, override=False, verbose=False)
else:
    # Log warning if .env file is not found in expected location
    import logging
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.warning(f".env file not found at expected location: {env_path}")

# Verify critical environment variables are loaded
if not os.environ.get('FERNET_KEY'):
    import logging
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.error(
        "CRITICAL: FERNET_KEY not loaded from .env file! "
        f"Checked path: {env_path}. "
        "Ensure .env file exists on server with FERNET_KEY variable."
    )

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
