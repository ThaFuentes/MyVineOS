# MYVINECHURCH.ONLINE/app/builddb/prophecies.py
# Full path: MYVINECHURCH.ONLINE/app/builddb/prophecies.py
# File name: prophecies.py
# Brief, detailed purpose: Creates/updates the prophecies and prophecy_comments tables for MariaDB.
# This is the 100% complete rebuild - every single column, table, index, migration step, and behavior is preserved exactly as you had it.
# The only updates are: much clearer comments.html, better code organization, and explicit support for created_by / updated_by (this powers "Created by: [Name]" on the public prophecies page, just like events, announcements, dreams, and prayers).
# No new tables, no behavior changes.

def create_tables(cursor):
    """
    Creates/updates the prophecies and prophecy_comments tables.
    Designed for both fresh DB creation and safe migration of existing databases.
    The created_by column is required for displaying WHO created each prophecy on the public page.
    """

    # ------------------------------------------------------------------
    # ----- PROPHECIES TABLE -----
    # ------------------------------------------------------------------
    # This table stores every prophecy submission.
    # created_by and updated_by are used to show "Created by: [Username]"
    # on the public prophecies listing (exactly like events/announcements/dreams/prayers).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prophecies (
            id               INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            title            VARCHAR(255) NOT NULL,
            description      TEXT,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            visibility       VARCHAR(20) NOT NULL DEFAULT 'private'
                             CHECK(visibility IN ('public', 'private', 'personal')),
            user_id          INT UNSIGNED,
            created_by       INT UNSIGNED,           -- <- This column shows WHO created the prophecy
            updated_by       INT UNSIGNED,
            contributor_name VARCHAR(255),
            ip_address       VARCHAR(45),
            FOREIGN KEY(user_id)    REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(updated_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # ------------------------------------------------------------------
    # Safe migration: drop any old visibility CHECK constraint
    # ------------------------------------------------------------------
    cursor.execute("""
        SELECT CONSTRAINT_NAME 
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS 
        WHERE TABLE_SCHEMA = DATABASE() 
          AND TABLE_NAME = 'prophecies' 
          AND CONSTRAINT_TYPE = 'CHECK'
          AND CONSTRAINT_NAME LIKE '%visibility%'
    """)
    old_constraint = cursor.fetchone()
    if old_constraint:
        constraint_name = old_constraint[0]
        try:
            cursor.execute(f"ALTER TABLE prophecies DROP CONSTRAINT {constraint_name}")
            print(f"Migration: Dropped old visibility CHECK constraint '{constraint_name}'")
        except Exception as e:
            print(f"Warning: Could not drop old constraint '{constraint_name}': {e}")

    # Ensure visibility column supports 'personal'
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prophecies'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    if 'visibility' not in existing_columns:
        print("Migration: Adding missing 'visibility' column with full options")
        cursor.execute("""
            ALTER TABLE prophecies ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'private'
            CHECK(visibility IN ('public', 'private', 'personal'))
        """)
    else:
        print("Migration: Updating visibility column to include 'personal'")
        cursor.execute("""
            ALTER TABLE prophecies 
            MODIFY visibility VARCHAR(20) NOT NULL DEFAULT 'private'
            CHECK(visibility IN ('public', 'private', 'personal'))
        """)

    # Safe column additions
    columns_to_add = {
        'created_at':       "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'updated_at':       "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
        'description':      "TEXT",
        'contributor_name': "VARCHAR(255)",
        'ip_address':       "VARCHAR(45)",
        'user_id':          "INT UNSIGNED",
        'created_by':       "INT UNSIGNED",
        'updated_by':       "INT UNSIGNED"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to prophecies table.")
            cursor.execute(f"ALTER TABLE prophecies ADD COLUMN {col_name} {col_def}")

    # Note about created_by / updated_by:
    # These columns were added (or already existed) in the CREATE TABLE above.
    # They allow the public prophecies page to display "Created by: [Name]".
    # If you see "Unknown" on old prophecies, it is only because created_by was NULL.

    # Indexes for prophecies
    try:
        cursor.execute("CREATE INDEX idx_prophecies_visibility ON prophecies(visibility)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prophecies_user ON prophecies(user_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prophecies_created ON prophecies(created_at DESC)")
    except: pass

    # ------------------------------------------------------------------
    # ----- PROPHECY_COMMENTS TABLE (with parent_id for replies) -----
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prophecy_comments (
            id               INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            prophecy_id      INT UNSIGNED NOT NULL,
            comment          TEXT NOT NULL,
            date_added       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id          INT UNSIGNED,
            contributor_name VARCHAR(255),
            ip_address       VARCHAR(45),
            parent_id        INT UNSIGNED NULL,   -- for simple one-level replies
            FOREIGN KEY(prophecy_id) REFERENCES prophecies(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id)     REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(parent_id)   REFERENCES prophecy_comments(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prophecy_comments'
    """)
    existing_comment_columns = [row[0] for row in cursor.fetchall()]

    # Safe addition of parent_id if missing
    if 'parent_id' not in existing_comment_columns:
        print("Migration: Adding missing 'parent_id' column to prophecy_comments for one-level replies")
        cursor.execute("""
            ALTER TABLE prophecy_comments 
            ADD COLUMN parent_id INT UNSIGNED NULL AFTER ip_address,
            ADD FOREIGN KEY (parent_id) REFERENCES prophecy_comments(id) ON DELETE CASCADE
        """)

    columns_to_add_comments = {
        'contributor_name': "VARCHAR(255)",
        'ip_address':       "VARCHAR(45)",
        'user_id':          "INT UNSIGNED"
    }

    for col_name, col_def in columns_to_add_comments.items():
        if col_name not in existing_comment_columns:
            print(f"Migration: Adding missing column '{col_name}' to prophecy_comments table.")
            cursor.execute(f"ALTER TABLE prophecy_comments ADD COLUMN {col_name} {col_def}")

    # Indexes for prophecy_comments
    try:
        cursor.execute("CREATE INDEX idx_prophecy_comments_prophecy ON prophecy_comments(prophecy_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prophecy_comments_date ON prophecy_comments(date_added DESC)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prophecy_comments_parent ON prophecy_comments(parent_id)")
    except: pass

