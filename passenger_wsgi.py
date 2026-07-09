# ================================================================
# myvineos.poweredby.top/passenger_wsgi.py
# CLEAN PASSENGER WSGI ENTRY POINT – NO SELF-IMPORT – NO RECURSION
# 1000% MINIMAL – points to main.py only
# Full 100% rebuild – security is priority #1
# ================================================================

import os
import sys

# Add current directory to Python path (safe)
sys.path.insert(0, os.path.dirname(__file__))

# Import the actual Flask application from main.py
from main import application