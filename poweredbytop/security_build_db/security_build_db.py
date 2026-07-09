# ================================================================
# poweredbytop/security_build_db/security_build_db.py
# PoweredByTop MariaDB Security Table Builder
# Discovers + runs create_tables from sibling modules (pbt_* tables)
# Aligned with main app/builddb/ pattern for consistency and robustness
# 100% FRESH - MARIADB ONLY
# ================================================================
# MARIADB ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# ================================================================
import pymysql
import os
import time
import importlib
import pkgutil
from pathlib import Path
from pymysql.err import OperationalError

def get_connection(max_retries=5, delay=1):
    """Create and return a MariaDB connection with retry logic (standalone for DDL).
    Fast-fail version (see main app/builddb/builddb.py for rationale).
    """
    host = os.getenv('MYSQL_HOST', 'localhost')
    user = os.getenv('MYSQL_USER', 'churchuser')
    password = os.getenv('MYSQL_PASSWORD', '')
    database = os.getenv('MYSQL_DATABASE', 'church_management')
    port = int(os.getenv('MYSQL_PORT', '3306'))
    attempt = 0
    while attempt < max_retries:
        try:
            conn = pymysql.connect(
                host=host,
                user=user,
                password=password,
                database=database,
                port=port,
                charset='utf8mb4',
                autocommit=False
            )
            if os.getenv('PBT_VERBOSE_BUILD', '0') == '1':
                print(f"PoweredByTop: Connected to MariaDB at {host}:{port}")
            return conn
        except OperationalError as e:
            attempt += 1
            wait = min(delay * (2 ** (attempt - 1)), 5)
            print(f"PoweredByTop connection attempt {attempt}/{max_retries} failed: {e}")
            print(f"Retrying in {wait} seconds...")
            time.sleep(wait)
    raise OperationalError("PoweredByTop failed to connect to MariaDB after multiple attempts. Check Docker container / creds / ./myvineos launcher.")

def build_all(verbose: bool = False, cursor=None) -> None:
    """
    Discover and run create_tables for all pbt security modules in this folder.
    Uses safe explicit order + remaining alpha. Per-table try/except for robustness.
    Call this from poweredbytop init to ensure tables exist on startup.
    If cursor provided (e.g. from main app builddb), use it (caller manages commit/close).
    """
    if os.getenv("SKIP_DB_BUILD") in ("1", "true", "yes", "TRUE") or os.getenv("SKIP_PBT_BUILD") in ("1", "true", "yes", "TRUE") or os.getenv("TESTING") == "1":
        print("[pbt-build] Skipping PoweredByTop security table build (SKIP_DB_BUILD / SKIP_PBT_BUILD / TESTING).")
        return

    if verbose:
        print("Starting PoweredByTop MariaDB security table build...")

    own_conn = False
    if cursor is None:
        conn = get_connection()
        cursor = conn.cursor()
        own_conn = True

    # Discover modules (like app/builddb/builddb.py)
    package_path = Path(__file__).parent
    modules = []
    for finder, name, ispkg in pkgutil.iter_modules([str(package_path)]):
        if name not in ['security_build_db', '__init__']:
            try:
                module = importlib.import_module(f'.{name}', package='poweredbytop.security_build_db')
                modules.append((name, module))
            except Exception as e:
                if verbose:
                    print(f"   Could not import {name}.py: {e}")

    # Explicit safe order (reputation first as it's core)
    ordered_names = [
        'security_scorer',   # pbt_reputation
        'security_events',   # pbt_security_events
        'security_stats',    # pbt_attack_stats
        'security_traffic',  # pbt_traffic
    ]

    ordered_modules = []
    remaining_modules = []

    for name, module in modules:
        if name in ordered_names:
            ordered_modules.append((ordered_names.index(name), name, module))
        else:
            remaining_modules.append((name, module))

    ordered_modules.sort(key=lambda x: x[0])
    ordered_modules = [m[2] for m in ordered_modules]

    remaining_modules.sort(key=lambda x: x[0])
    remaining_modules = [m[1] for m in remaining_modules]

    execution_order = ordered_modules + remaining_modules

    for module in execution_order:
        module_name = module.__name__.split('.')[-1]
        if hasattr(module, 'create_tables'):
            if verbose:
                print(f"  -> Running create_tables from {module_name}.py")
            try:
                module.create_tables(cursor)
            except Exception as e:
                print(f"   Error in {module_name}.py (non-fatal for other tables): {e}")
                # do not raise - allow partial success, tables may exist
        else:
            if verbose:
                print(f"  -> Skipping {module_name}.py (no create_tables)")

    if own_conn:
        conn.commit()
        conn.close()

    if verbose:
        print("PoweredByTop: Security table build complete (pbt_* tables)")

if __name__ == '__main__':
    build_all(verbose=True)