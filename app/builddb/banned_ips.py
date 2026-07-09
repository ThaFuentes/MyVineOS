# myvinechurchonline/app/builddb/banned_ips.py
# Full path: myvinechurchonline/app/builddb/banned_ips.py
# File name: banned_ips.py
# Brief, detailed purpose: Creates the banned_ips table for MariaDB.
# Tracks abusive IP addresses for blocking in guest submission routes.
# Primary key on ip_address (VARCHAR(45) to support IPv4/IPv6 and fix MariaDB TEXT PK limitation).
# Audit fields for who banned and reason.
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module – called from builddb.py during DB initialization.
# Fixes errno 150 by matching banned_by type (INT UNSIGNED) to users.id.

def create_tables(cursor):
    """
    Creates/updates the banned_ips table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- BANNED_IPS TABLE -----
    # Changed banned_by to INT UNSIGNED to match users.id and fix errno: 150
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_ips (
            ip_address VARCHAR(45) PRIMARY KEY,          
            banned_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            banned_by  INT UNSIGNED,                     
            reason     TEXT,
            FOREIGN KEY(banned_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'banned_ips'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'banned_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'banned_by': "INT UNSIGNED",
        'reason':    "TEXT"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to banned_ips table.")
            cursor.execute(f"ALTER TABLE banned_ips ADD COLUMN {col_name} {col_def}")

    # Additional indexes
    # MariaDB 'CREATE INDEX IF NOT EXISTS' is supported in recent versions,
    # but using a try/except block for maximum compatibility during build.
    try:
        cursor.execute("CREATE INDEX idx_banned_ips_by ON banned_ips(banned_by)")
    except:
        pass

    try:
        cursor.execute("CREATE INDEX idx_banned_ips_at ON banned_ips(banned_at DESC)")
    except:
        pass