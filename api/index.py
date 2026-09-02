import os
import sys

# Ensure root project directory is in the Python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Import the Flask application instance for Vercel's serverless runtime
from app import app
