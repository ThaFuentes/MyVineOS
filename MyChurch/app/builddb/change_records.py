# myvinechurchonline/app/builddb/change_records.py
# Full path: myvinechurchonline/app/builddb/change_records.py
# File name: change_records.py
# Brief, detailed purpose: Creates the change_records table for MariaDB audit logging.
# Logs all significant actions (create/update/delete/view/email etc.) with user accountability.
# Fields: user_id (FK to users), action, optional target_id/username, details, timestamp.
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module - called from builddb.py during DB initialization.
# Updated user_id to INT UNSIGNED to match users.id and fix MariaDB Errno 150.

def create_tables(cursor):
    """
    Creates/updates the change_records (audit log) table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- CHANGE_RECORDS TABLE -----
    # user_id must be INT UNSIGNED to match the primary key in the users table.
    # action changed to VARCHAR to support indexing.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_records (
            id              INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id         INT UNSIGNED,
            action          VARCHAR(100) NOT NULL,
            target_id       INT UNSIGNED,
            target_username VARCHAR(255),
            change_details  TEXT,
            timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'change_records'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'user_id':         "INT UNSIGNED",
        'target_id':       "INT UNSIGNED",
        'target_username': "VARCHAR(255)",
        'change_details':  "TEXT",
        'timestamp':       "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding or updating column '{col_name}' in change_records table.")
            cursor.execute(f"ALTER TABLE change_records ADD COLUMN {col_name} {col_def}")

    # Indexes for common audit queries
    # Using try/except for index creation to ensure smooth execution even if IF NOT EXISTS is unsupported
    try:
        cursor.execute("CREATE INDEX idx_change_records_user ON change_records(user_id)")
    except: pass

    try:
        cursor.execute("CREATE INDEX idx_change_records_timestamp ON change_records(timestamp DESC)")
    except: pass

    try:
        cursor.execute("CREATE INDEX idx_change_records_action ON change_records(action)")
    except: pass