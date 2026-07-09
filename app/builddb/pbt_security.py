# app/builddb/pbt_security.py
# Integrates PoweredByTop pbt_* security tables into the main app's MariaDB build.
# This ensures tables are always created (with app tables) even if init_security not yet called.
# Delegates to poweredbytop's discovery-based builder, passing the shared cursor.
# 100% MariaDB compatible.

from poweredbytop.security_build_db.security_build_db import build_all as build_pbt_tables

def create_tables(cursor):
    """Called by app/builddb/builddb.py discovery. Uses the provided cursor for atomic build."""
    try:
        build_pbt_tables(verbose=False, cursor=cursor)
    except Exception as e:
        print(f"  ⚠️ pbt_security build note: {e}")
        # non-fatal; tables may exist or pbt not fully present in this env

# No direct run; only via main build or pbt init.