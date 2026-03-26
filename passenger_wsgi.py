import os
import sys

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

# Set Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "serensa.settings")

# Import and run Django WSGI application
from serensa.wsgi import application
