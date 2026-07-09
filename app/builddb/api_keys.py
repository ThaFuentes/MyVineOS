# myvinechurchonline/app/builddb/api_keys.py
# Full path: myvinechurchonline/app/builddb/api_keys.py
# File name: api_keys.py
# Brief, detailed purpose: Creates the api_keys table for MariaDB.
# Stores AI service API keys (service unique, api_key encrypted in app before storage, enabled flag).
# Owner/Admin management via future settings page.
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module – called from builddb.py during DB initialization.
# Safe to run repeatedly.

def create_tables(cursor):
    """
    Creates/updates the api_keys table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- API_KEYS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id         INT PRIMARY KEY AUTO_INCREMENT,
            service    TEXT UNIQUE NOT NULL,                 -- e.g., 'gemini', 'openai', 'grok'
            api_key    TEXT NOT NULL,                        -- Stored encrypted in application logic
            enabled    INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'api_keys'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'enabled':    "INTEGER DEFAULT 1",
        'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to api_keys table.")
            cursor.execute(f"ALTER TABLE api_keys ADD COLUMN {col_name} {col_def}")

    # Index on service is implicit due to UNIQUE constraint – no additional indexes needed