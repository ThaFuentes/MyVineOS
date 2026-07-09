# myvinechurchonline/app/builddb/user_widgets.py
# Full path: myvinechurchonline/app/builddb/user_widgets.py
# File name: user_widgets.py
# Brief, detailed purpose: Creates the user_widgets table for MariaDB.
# Enables per-user dashboard widget customization (enable/disable specific widgets).
# Unique constraint prevents duplicate widget entries per user.
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module – called from builddb.py during DB initialization.
# All user-related FKs use UNSIGNED INT to match users.id type and fix errno 150 FK mismatch.

def create_tables(cursor):
    """
    Creates/updates the user_widgets table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- USER_WIDGETS TABLE -----
    # 1. user_id changed to INT UNSIGNED to match users.id.
    # 2. widget_name changed to VARCHAR(100) to allow UNIQUE constraint and indexing.
    # 3. is_enabled changed to TINYINT(1) for standard boolean storage.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_widgets (
            id          INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id     INT UNSIGNED NOT NULL,
            widget_name VARCHAR(100) NOT NULL,
            is_enabled  TINYINT(1) DEFAULT 1,
            UNIQUE(user_id, widget_name),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_widgets'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'is_enabled': "TINYINT(1) DEFAULT 1",
        'user_id':    "INT UNSIGNED NOT NULL",
        'widget_name': "VARCHAR(100) NOT NULL"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding or updating column '{col_name}' in user_widgets table.")
            cursor.execute(f"ALTER TABLE user_widgets ADD COLUMN {col_name} {col_def}")

    # Indexes for common queries
    try:
        cursor.execute("CREATE INDEX idx_user_widgets_user ON user_widgets(user_id)")
    except:
        pass

    try:
        cursor.execute("CREATE INDEX idx_user_widgets_enabled ON user_widgets(is_enabled)")
    except:
        pass