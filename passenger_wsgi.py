import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from a2wsgi import ASGIMiddleware
from dashboard.app import app

application = ASGIMiddleware(app)