import os
import sys

# Add the app directory to the Python path
APP_DIR = os.path.dirname(__file__)
sys.path.insert(0, APP_DIR)


def _load_env_file(env_path):
	if not os.path.exists(env_path):
		return
	with open(env_path, "r", encoding="utf-8") as f:
		for raw in f:
			line = raw.strip()
			if not line or line.startswith("#") or "=" not in line:
				continue
			key, value = line.split("=", 1)
			key = key.strip()
			value = value.strip().strip('"').strip("'")
			# Keep platform-defined env values if they already exist.
			os.environ.setdefault(key, value)


# Load optional env files used in cPanel deployments.
_load_env_file(os.path.join(APP_DIR, ".env"))
_load_env_file(os.path.join(APP_DIR, ".env.cPanel"))

# Set Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "serensa.settings")

# Import and run Django WSGI application
from serensa.wsgi import application
