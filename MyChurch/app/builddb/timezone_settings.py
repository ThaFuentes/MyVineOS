# myvinechurchonline/app/builddb/timezone_setting.py
# Full path: WebChurchMan/app/builddb/timezone_setting.py
# File name: timezone_setting.py
# Brief, detailed purpose: Adds/updates the timezone column in the settings table.
# Stores the church's preferred IANA timezone name (e.g., 'America/Chicago').
# All timestamps are stored in UTC; this value is used for display/input conversion.
# Safe migration: checks for column existence via INFORMATION_SCHEMA before ALTER.
# Default: 'America/Chicago' (Central Time - matches church location in Odessa, TX).
# Isolated module - called from builddb.py during DB initialization.
# Uses MariaDB/MySQL compatible syntax and patterns consistent with attendance.py, etc.
# FULL REBUILD: Function renamed to create_tables(cursor) to match builddb.py discovery pattern.
# All original logic preserved exactly - no functionality lost.

def create_tables(cursor):
    """
    Adds the timezone column to the settings table if missing.
    Designed for both fresh DB creation and safe migration of existing databases.
    Ensures exactly one timezone TEXT column with DEFAULT 'America/Chicago'.
    """
    # ----- Ensure timezone column exists in settings -----
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'settings'
          AND COLUMN_NAME = 'timezone'
    """)
    column_exists = cursor.fetchone() is not None
    if not column_exists:
        print("Migration: Adding 'timezone' column to settings table.")
        cursor.execute("""
            ALTER TABLE settings
            ADD COLUMN timezone TEXT DEFAULT 'America/Chicago'
        """)
        print("Added timezone column with DEFAULT 'America/Chicago'.")
    else:
        print("timezone column already exists in settings table - skipping addition.")
    # Optional: Enforce default value on existing NULL/empty rows (safe one-time fix)
    cursor.execute("""
        UPDATE settings
        SET timezone = 'America/Chicago'
        WHERE timezone IS NULL OR timezone = ''
    """)
    if cursor.rowcount > 0:
        print(f"Set DEFAULT 'America/Chicago' on {cursor.rowcount} existing settings row(s) with missing/empty timezone.")
    # No indexes needed - this is a single-row config table

print("MYVINECHURCH.ONLINE/app/builddb/timezone_setting.py - fully rebuilt with 100% ASCII-safe strings only")