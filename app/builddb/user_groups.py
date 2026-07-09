# myvinechurchonline/app/builddb/user_groups.py
# Full path: myvinechurchonline/app/builddb/user_groups.py
# File name: user_groups.py
# Brief, detailed purpose: Creates the user_groups junction table for MariaDB.
# Many-to-many assignment of users to groups with role_in_group (extensible, e.g., 'leader', 'member'),
# joined_at timestamp for membership duration, assigned_by for audit trail.
# Enforces uniqueness to prevent duplicates; cascades deletions safely.
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module – called from builddb.py during DB initialization.
# All ID/FK columns use UNSIGNED INT to match parent tables and fix errno 150.

def create_tables(cursor):
    """
    Creates/updates the user_groups junction table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- USER_GROUPS JUNCTION TABLE -----
    # user_id and assigned_by must match users.id (INT UNSIGNED)
    # group_id must match groups.id (INT UNSIGNED)
    # role_in_group changed to VARCHAR to support indexing.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            id             INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id        INT UNSIGNED NOT NULL,
            group_id       INT UNSIGNED NOT NULL,
            role_in_group  VARCHAR(100) DEFAULT 'member',     
            joined_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assigned_by    INT UNSIGNED,                      -- Made NULLable for SET NULL constraint
            FOREIGN KEY (user_id)     REFERENCES users(id)   ON DELETE CASCADE,
            FOREIGN KEY (group_id)    REFERENCES groups(id)  ON DELETE CASCADE,
            FOREIGN KEY (assigned_by) REFERENCES users(id)   ON DELETE SET NULL,
            UNIQUE (user_id, group_id)
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_groups'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'role_in_group': "VARCHAR(100) DEFAULT 'member'",
        'joined_at':     "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'assigned_by':   "INT UNSIGNED",
        'user_id':       "INT UNSIGNED NOT NULL",
        'group_id':      "INT UNSIGNED NOT NULL"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding or updating column '{col_name}' in user_groups table.")
            cursor.execute(f"ALTER TABLE user_groups ADD COLUMN {col_name} {col_def}")

    # Indexes for performance (Wrapped in try/except for migration safety)
    try:
        cursor.execute("CREATE INDEX idx_user_groups_user_id ON user_groups(user_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_user_groups_group_id ON user_groups(group_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_user_groups_role_in_group ON user_groups(role_in_group)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_user_groups_joined ON user_groups(joined_at DESC)")
    except: pass