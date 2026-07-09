# myvinechurchonline/app/builddb/builddb.py
# Full path: myvinechurchonline/app/builddb/builddb.py
# File name: builddb.py
# Brief, detailed purpose: Main database initialization script for MariaDB.
# Automatically discovers all Python modules in the builddb folder (excluding __init__.py and itself),
# imports them dynamically, and executes their create_tables(cursor) functions in SAFE ORDER.
# SAFE EXPLICIT ORDER to avoid FK constraint errors (errno 150):
#   1. users.py (base for all user FKs)
#   2. groups.py (required for user_groups and attendance group_id)
#   3. user_groups.py
#   4. attendance.py (references users and groups)
#   5. family_relations.py
#   6. member_roles.py
#   7. user_widgets.py
#   8. timezone_setting.py (runs last – ALTER on settings table, safe anytime after settings exists)
#   9. Any remaining modules alphabetically
# Added robust retry logic with exponential backoff for connection/initialization issues.
# Verbose mode (default True when run directly) for debugging; quiet success message otherwise.
# FULL REBUILD: Added timezone_setting to explicit order (safe position at end).

import pymysql
import importlib
import pkgutil
from pathlib import Path
import os
import time
from pymysql.err import OperationalError


def get_connection(max_retries=5, delay=1):
    """Create and return a single MariaDB connection with retry logic.
    Keeps retries for transient races (e.g. docker just coming up), but fails fast.
    Long hangs (30min+) on unreachable DB are avoided; launcher does the patient wait.
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
            print(f"Successfully connected to MariaDB at {host}:{port}")
            return conn
        except OperationalError as e:
            attempt += 1
            wait = min(delay * (2 ** (attempt - 1)), 5)  # Exponential but capped
            print(f"Connection attempt {attempt}/{max_retries} failed: {e}")
            print(f"Retrying in {wait} seconds...")
            time.sleep(wait)

    raise OperationalError("Failed to connect to MariaDB after multiple attempts. Check Docker container status, .env creds, or run via ./myvineos (it waits + exports correct MYSQL_*).")


def build_all(verbose: bool = False) -> None:
    """
    Discover and run create_tables for all modules in this folder.
    SAFE EXPLICIT ORDER to avoid FK constraint errors (errno 150).
    """
    if os.getenv("SKIP_DB_BUILD") in ("1", "true", "yes", "TRUE") or os.getenv("TESTING") == "1":
        print("[builddb] Skipping DB build (SKIP_DB_BUILD or TESTING env set).")
        return

    if verbose:
        print("Starting MariaDB database build...")

    conn = get_connection()
    cursor = conn.cursor()

    # Discover all modules
    package_path = Path(__file__).parent
    modules = []
    for finder, name, ispkg in pkgutil.iter_modules([str(package_path)]):
        if name not in ['builddb', '__init__']:
            module = importlib.import_module(f'.{name}', package='app.builddb')
            modules.append((name, module))

    # Explicit safe order (critical dependencies first)
    ordered_names = [
        'users',           # Base table – all user FKs depend on this
        'groups',          # Needed for user_groups and attendance.group_id
        'user_groups',     # Junction table
        'attendance',      # References users and groups
        'family_relations',
        'member_roles',
        'user_widgets',
        'timezone_setting',  # ← ADDED: Runs last – safe ALTER on settings table
        'comment_moderation',  # After all comment tables exist
    ]

    ordered_modules = []
    remaining_modules = []

    for name, module in modules:
        if name in ordered_names:
            ordered_modules.append((ordered_names.index(name), name, module))
        else:
            remaining_modules.append((name, module))

    # Sort ordered by index
    ordered_modules.sort(key=lambda x: x[0])
    ordered_modules = [m[2] for m in ordered_modules]

    # Sort remaining alphabetically
    remaining_modules.sort(key=lambda x: x[0])
    remaining_modules = [m[1] for m in remaining_modules]

    # Final execution order
    execution_order = ordered_modules + remaining_modules

    # Run in order
    for module in execution_order:
        module_name = module.__name__.split('.')[-1]
        if hasattr(module, 'create_tables'):
            if verbose:
                print(f"  → Running create_tables from {module_name}.py")
            try:
                module.create_tables(cursor)
            except Exception as e:
#                 print(f"  ⚠️ Critical error in {module_name}.py: {e}")
                raise
        else:
            if verbose:
                print(f"  → Skipping {module_name}.py (no create_tables function)")

    conn.commit()
    conn.close()

    print("All build is good")


if __name__ == '__main__':
    build_all(verbose=True)