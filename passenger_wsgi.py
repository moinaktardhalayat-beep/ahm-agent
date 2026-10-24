import sys, os, subprocess

# Auto-install packages on startup
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
except Exception as e:
    pass

# Load app
sys.path.insert(0, os.path.dirname(__file__))
from a2wsgi import ASGIMiddleware
from dashboard.app import app

application = ASGIMiddleware(app)