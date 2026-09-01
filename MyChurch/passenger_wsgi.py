import sys
import os

# Force UTF-8 encoding to fix emoji/unicode errors
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Add project directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import your Flask app from main.py
from main import app as application