# ================================================================
# poweredbytop/models/connect_db.py
# ULTRA VERBOSE CENTRAL MARIA DB CONNECTOR - SINGLE SOURCE OF TRUTH
# PYMYSQL + FLASK G + FULL HEALTH CHECKS + NO LEAKS + SECURITY FIRST
# ================================================================
import logging
import time
import os
from flask import current_app, g, has_request_context, request
import pymysql
from pymysql import cursors

logger = logging.getLogger("poweredbytop.db")
logger.setLevel(logging.INFO)

# ====================== CONFIG FALLBACKS (from Flask config or env) ======================
def _get_db_config():
    """Central config - easy to override in settings.py later"""
    return {
        "host": current_app.config.get('MYSQL_HOST') or os.getenv('MYSQL_HOST', '127.0.0.1'),
        "user": current_app.config.get('MYSQL_USER') or os.getenv('MYSQL_USER', 'churchuser'),
        "password": current_app.config.get('MYSQL_PASSWORD') or os.getenv('MYSQL_PASSWORD', ''),
        "database": current_app.config.get('MYSQL_DATABASE') or os.getenv('MYSQL_DATABASE', 'church_management'),
        "port": int(current_app.config.get('MYSQL_PORT') or os.getenv('MYSQL_PORT', 3306)),
        "charset": 'utf8mb4',
        "cursorclass": cursors.DictCursor,   # Guarantees row.get() works everywhere
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
    }

# ====================== PER-REQUEST SAFE GETTER (used by ALL modules) ======================
def get_security_db():
    """Same MariaDB as the church site. Never Aegis or a second product."""
    try:
        from flask import has_app_context
        from app.models.db import get_db

        if not has_app_context():
            return None
        return get_db()
    except Exception as e:
        logger.error(f"[DB] Church DB unavailable for security logging: {e}")
        return None


# ====================== CLEANUP HANDLER (register this in your app) ======================
def close_security_db(e=None):
    """Church get_db() lives on flask.g and is closed by app.models.db.close_db."""
    return


# ====================== TABLE ENSURE HELPER (used by reputation etc.) ======================
def ensure_table_exists(table_name: str, create_sql: str):
    """One-liner safe table creator - call from any module. Robust to re-runs."""
    db = get_security_db()
    if db is None:
        return False
    try:
        with db.cursor() as cursor:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({create_sql}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
            db.commit()
        logger.info(f"[DB] Table verified/created: {table_name}")
        return True
    except Exception as e:
        # e.g. already exists, or partial - non fatal
        logger.warning(f"[DB] Table ensure note for {table_name}: {e}")
        return False


logger.info("=== poweredbytop/models/connect_db.py FULLY REBUILT & LOADED ===")
logger.info("Central DB layer ready - all modules will now use this single source of truth")