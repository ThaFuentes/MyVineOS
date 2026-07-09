# ================================================================
# poweredbytop/__init__.py
# MAIN GATEKEEPER - FORCES EVERY REQUEST THROUGH FULL PIPELINE
# 100% FRESH REBUILD - NO OLD CODE - SECURITY FIRST
# ================================================================
# MARIADB ONLY - EXACT DB TABLES ONLY - USES core/security.py
# ================================================================

import logging
import os
from flask import Flask

# ====================== SAFE IMPORTS ======================
from poweredbytop.config.settings import FULL_SECURITY_PIPELINE_ENABLED, DEBUG_MODE
from poweredbytop.core.security import before_request_security, teardown_security
from poweredbytop.auth.session import apply_secure_session_config
from poweredbytop.utils.helpers import logger
from poweredbytop.models.connect_db import close_security_db
from poweredbytop.security_build_db.security_build_db import build_all as build_pbt_tables

logger("poweredbytop/__init__.py loading - full pipeline active")

def init_security(app: Flask) -> Flask:
    """Call this in your Flask app to enable the complete PoweredByTop security layer"""
    logger("=== POWEREDBYTOP SECURITY INITIALIZING ===")

    # Apply hardened session settings
    apply_secure_session_config(app)

    # Auto-build pbt_* security tables in MariaDB on startup (robust, like main app builddb)
    # Runs outside request context using direct connect + retries. Safe/no-op if tables exist.
    # Skippable for tests / import verification (use SKIP_DB_BUILD=1 or SKIP_PBT_BUILD=1).
    if not (os.getenv("SKIP_DB_BUILD") in ("1", "true", "yes", "TRUE") or os.getenv("SKIP_PBT_BUILD") in ("1", "true", "yes", "TRUE") or os.getenv("TESTING") == "1"):
        try:
            build_pbt_tables(verbose=DEBUG_MODE)
        except Exception as build_err:
            logger(" PoweredByTop pbt table build warning (tables may already exist or DB unavailable): " + str(build_err))
    else:
        logger("[pbt] Skipping pbt table build due to SKIP_* / TESTING env.")

    # Attach full security pipeline (this replaces all old middleware/db_guard)
    @app.before_request
    def pbt_before_request():
        return before_request_security()

    @app.teardown_request
    def pbt_teardown(exception=None):
        teardown_security(exception)
        # Ensure pbt security DB connections are always closed (prevents leaks)
        close_security_db(exception)

    # Also register on appcontext for extra safety (e.g. errors before request teardown)
    @app.teardown_appcontext
    def pbt_close_db(e=None):
        close_security_db(e)

    if DEBUG_MODE:
        logger("DEBUG MODE ENABLED - full pipeline logging active")
    else:
        logger("Production security pipeline loaded and active")

    logger("=== POWEREDBYTOP FULL PIPELINE READY ===")
    return app

# Alias for backward compatibility with any existing calls
protect_app = init_security

logger("poweredbytop/__init__.py - 100% fresh rebuild loaded successfully (full pipeline active)")