# wsgi.py
# Full path: WebChurchMan/wsgi.py
# File name: wsgi.py
# Brief, detailed purpose:
#   Production WSGI entry point required by HostM.
#   Directly imports the exact "app" object created in your main.py – 100% YOUR script.
#   This is the version that makes HostM run YOUR code (main.py) instead of any default or generic loader.
#   The "It works!" page appears when HostM falls back to a generic Python handler (usually because wsgi.py is missing or wrong).
#   Replace the current wsgi.py with this exact content – it will force HostM to use your main.py.

from main import app as application