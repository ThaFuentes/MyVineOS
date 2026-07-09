# ================================================================
# main.py (myvineos.poweredby.top/main.py)
# NORMAL FLASK APP + POWEREDBYTOP SECURITY WRAPPER
# 100% FRESH REBUILD - CLEAN - USES NEW init_security
# ================================================================
# MARIADB ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# ================================================================

import os
import sys
from dotenv import load_dotenv

# ====================== PROJECT ROOT ======================
# Portable: use the directory containing this main.py
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
print("Project root detected -> " + PROJECT_ROOT)

# ====================== LOAD ENVIRONMENT ======================
# load_dotenv will not override existing env vars (so launcher can force dev DB creds)
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# ====================== IMPORT REAL APP + SECURITY ======================
try:
    from app import create_app
    from poweredbytop import init_security
    print("Successfully imported create_app and init_security")
except Exception as e:
    print("IMPORT ERROR: " + str(e))
    raise

# ====================== CREATE APP + APPLY FULL SECURITY ======================
app = create_app()
# Security is now initialized inside create_app() for early pipeline registration.
# (init_security call removed here to avoid double registration; main.py still imports for WSGI compat)
application = app                 # Passenger / WSGI needs this exact name

print("================================================================")
print("Site WSGI loaded successfully with PoweredByTop security")
print("All requests now go through the complete security pipeline")
print("================================================================")

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("DEBUG_MODE", "False").lower() == "true"
    print("Starting development server on " + host + ":" + str(port) + " (debug=" + str(debug) + ")")
    app.run(host=host, port=port, debug=debug, use_reloader=False)