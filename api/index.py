import os

from serensa.wsgi import application

# Vercel Python runtime looks for `app` by convention.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "serensa.settings")
app = application
