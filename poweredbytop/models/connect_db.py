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
    """Central config – easy to override in settings.py later"""
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
    """
    Returns a healthy DictCursor connection.
    - Only works inside Flask request context
    - Stores in g.pbt_db for the lifetime of the request
    - Full health ping + reconnect logic
    - Zero connection leaks
    - Graceful total failure fallback
    """
    if not has_request_context():
        logger.warning("[DB] Called outside request context → skipping (safe)")
        return None

    # Reuse existing connection if healthy
    if hasattr(g, 'pbt_db') and g.pbt_db is not None:
        try:
            g.pbt_db.ping(reconnect=True)  # Keep-alive + detect dead connections
            logger.debug(f"[DB] Reusing healthy connection | IP={request.remote_addr}")
            return g.pbt_db
        except Exception as e:
            logger.warning(f"[DB] Stale connection detected, creating new: {e}")
            g.pbt_db = None

    # Create fresh connection
    try:
        config = _get_db_config()
        db = pymysql.connect(**config)
        db.autocommit(False)  # We control commits manually for safety (critical for reputation)

        # Store in Flask g for automatic cleanup
        g.pbt_db = db

        ip = request.remote_addr or "unknown"
        logger.info(f"[DB] NEW CONNECTION ACQUIRED | IP={ip} | Database={config['database']}")

        # Track for N1 / bulkhead (best effort; increments on security DB use)
        if has_request_context():
            g.query_count = getattr(g, 'query_count', 0) + 1

        return db

    except Exception as e:
        logger.error(f"[DB] CRITICAL CONNECTION FAILURE: {str(e)}")
        logger.error(f"[DB] Config used → Host={config.get('host')} | DB={config.get('database')}")
        return None


# ====================== CLEANUP HANDLER (register this in your app) ======================
def close_security_db(e=None):
    """Flask teardown_request / teardown_appcontext handler – prevents leaks.
    Always safe to call; handles missing request context.
    """
    db = g.pop('pbt_db', None)
    if db is not None:
        try:
            db.commit()          # Final safety net commit (our autocommit=False)
            db.close()
            ip = "unknown"
            try:
                if has_request_context():
                    ip = getattr(request, 'remote_addr', 'unknown')
            except Exception:
                pass
            logger.debug(f"[DB] Connection closed cleanly | IP={ip}")
        except Exception as close_err:
            logger.warning(f"[DB] Cleanup warning (non-fatal): {close_err}")


# ====================== TABLE ENSURE HELPER (used by reputation etc.) ======================
def ensure_table_exists(table_name: str, create_sql: str):
    """One-liner safe table creator – call from any module. Robust to re-runs."""
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