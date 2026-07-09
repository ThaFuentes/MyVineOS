# passenger_wsgi.py - Clean version for MyVineOS (loads main.py)
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import the Flask app from main.py as 'application' (required by Passenger)
from main import app as application