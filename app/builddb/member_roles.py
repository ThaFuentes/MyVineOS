# myvinechurchonline/app/builddb/member_roles.py
# Full path: myvinechurchonline/app/builddb/member_roles.py
# File name: member_roles.py
# Brief, detailed purpose: Creates the member_roles table for MariaDB.
# Enables many-to-many assignment of roles to users (multiple roles per user).
# Supports future flexible permission systems beyond the single 'role' column in users table.
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module – called from builddb.py during DB initialization.
# Fixes MariaDB Errno 150 by using UNSIGNED INT and VARCHAR for indexing.

def create_tables(cursor):
    """
    Creates/updates the member_roles table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- MEMBER_ROLES TABLE -----
    # user_id must be INT UNSIGNED to match users.id.
    # role_name must be VARCHAR to allow the unique index to function.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS member_roles (
            id        INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id   INT UNSIGNED NOT NULL,
            role_name VARCHAR(50) NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'member_roles'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'user_id':   "INT UNSIGNED NOT NULL",
        'role_name': "VARCHAR(50) NOT NULL"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding or updating column '{col_name}' in member_roles table.")
            cursor.execute(f"ALTER TABLE member_roles ADD COLUMN {col_name} {col_def}")

    # Indexes for common queries (Wrapped in try/except for migration safety)
    try:
        cursor.execute("CREATE INDEX idx_member_roles_user ON member_roles(user_id)")
    except: pass

    try:
        cursor.execute("CREATE INDEX idx_member_roles_role ON member_roles(role_name)")
    except: pass

    # Unique index to prevent the same user from having the same role twice
    try:
        cursor.execute("CREATE UNIQUE INDEX idx_member_roles_unique ON member_roles(user_id, role_name)")
    except: pass