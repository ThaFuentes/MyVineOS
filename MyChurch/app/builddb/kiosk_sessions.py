# myvinechurchonline/app/builddb/kiosk_sessions.py
# Full path: WebChurchMan/app/builddb/kiosk_sessions.py
# File name: kiosk_sessions.py
# Brief, detailed purpose: Creates the kiosk_sessions table for MariaDB.
# Tracks active attendance kiosk sessions (token-based, secure, expirable).
# Core fields: token (UNIQUE), created_by, created_at, expires_at, active.
# Used for public kiosk access - token required, no login.
# Tokens auto-expire or manual close.
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module - called from builddb.py during DB initialization.
# FK to users.id for creator.

def create_tables(cursor):
    """
    Creates/updates the kiosk_sessions table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- KIOSK_SESSIONS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kiosk_sessions (
            id          INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            token       VARCHAR(255) UNIQUE NOT NULL,
            created_by  INT UNSIGNED NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at  TIMESTAMP NOT NULL,
            active      TINYINT(1) DEFAULT 1,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'kiosk_sessions'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'token':       "VARCHAR(255) UNIQUE NOT NULL",
        'created_by':  "INT UNSIGNED NOT NULL",
        'created_at':  "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'expires_at':  "TIMESTAMP NOT NULL",
        'active':      "TINYINT(1) DEFAULT 1"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to kiosk_sessions table.")
            cursor.execute(f"ALTER TABLE kiosk_sessions ADD COLUMN {col_name} {col_def}")

    # Indexes for common queries
    try:
        cursor.execute("CREATE INDEX idx_kiosk_token ON kiosk_sessions(token)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_kiosk_active ON kiosk_sessions(active)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_kiosk_expires ON kiosk_sessions(expires_at)")
    except: pass

    print("Kiosk_sessions table synchronization complete (MariaDB). Ready for secure token-based kiosk.")