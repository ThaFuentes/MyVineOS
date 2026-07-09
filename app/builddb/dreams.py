# MYVINECHURCH.ONLINE/app/builddb/dreams.py
# Full path: MYVINECHURCH.ONLINE/app/builddb/dreams.py
# File name: dreams.py
# Brief, detailed purpose: Creates/updates the dreams and dream_comments tables for MariaDB.
# This is the 100% complete rebuild — every single column, table, index, migration step, and behavior is preserved exactly as you had it.
# The only updates are: much clearer comments.html, better code organization, and explicit documentation around the created_by column (this powers "Created by: [Name]" on the public dreams page, just like events, announcements, prayers, and sermons).
# No new columns, no new tables, no behavior changes.

def create_tables(cursor):
    """
    Creates/updates the dreams and dream_comments tables.
    Designed for both fresh DB creation and safe migration of existing databases.
    The created_by column is required for displaying WHO created each dream/vision on the public page.
    """

    # ------------------------------------------------------------------
    # ----- DREAMS TABLE -----
    # ------------------------------------------------------------------
    # This table stores every dream/vision submission.
    # created_by and updated_by are used to show "Created by: [Username]"
    # on the public dreams listing (exactly like events, announcements, prayers, and sermons).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dreams (
            id               INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            title            VARCHAR(255) NOT NULL,
            description      TEXT NOT NULL,
            notes            TEXT,
            category         VARCHAR(100),
            date_occurred    DATETIME,
            date_posted      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visibility       VARCHAR(20) NOT NULL DEFAULT 'private'
                             CHECK(visibility IN ('public', 'private', 'personal')),
            is_approved      TINYINT(1) DEFAULT 1,
            comments_count   INTEGER DEFAULT 0,
            user_id          INT UNSIGNED,
            created_by       INT UNSIGNED,           -- ← This column shows WHO created the dream/vision
            updated_by       INT UNSIGNED,
            approved_by      INT UNSIGNED,
            contributor_name VARCHAR(255),
            ip_address       VARCHAR(45),
            FOREIGN KEY(user_id)     REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by)  REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(updated_by)  REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(approved_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # ------------------------------------------------------------------
    # Safe migration: handle old visibility CHECK constraint and add 'personal'
    # ------------------------------------------------------------------
    cursor.execute("""
        SELECT CONSTRAINT_NAME 
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS 
        WHERE TABLE_SCHEMA = DATABASE() 
          AND TABLE_NAME = 'dreams' 
          AND CONSTRAINT_TYPE = 'CHECK'
          AND CONSTRAINT_NAME LIKE '%visibility%'
    """)
    old_constraint = cursor.fetchone()
    if old_constraint:
        constraint_name = old_constraint[0]
        try:
            cursor.execute(f"ALTER TABLE dreams DROP CONSTRAINT {constraint_name}")
            print(f"Migration: Dropped old visibility CHECK constraint '{constraint_name}'")
        except Exception as e:
            print(f"Warning: Could not drop old constraint '{constraint_name}': {e}")

    # Ensure visibility column has correct definition including 'personal'
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'dreams'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    if 'visibility' not in existing_columns:
        print("Migration: Adding missing 'visibility' column with full options")
        cursor.execute("""
            ALTER TABLE dreams ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'private'
            CHECK(visibility IN ('public', 'private', 'personal'))
        """)
    else:
        print("Migration: Updating visibility column to include 'personal'")
        cursor.execute("""
            ALTER TABLE dreams 
            MODIFY visibility VARCHAR(20) NOT NULL DEFAULT 'private'
            CHECK(visibility IN ('public', 'private', 'personal'))
        """)

    # Remove is_personal column if it exists (deprecated)
    if 'is_personal' in existing_columns:
        print("Migration: Removing deprecated 'is_personal' column")
        try:
            cursor.execute("ALTER TABLE dreams DROP COLUMN is_personal")
        except Exception as e:
            print(f"Warning: Could not drop is_personal column: {e}")

    # Safe column additions
    columns_to_add = {
        'notes':            "TEXT",
        'category':         "VARCHAR(100)",
        'date_occurred':    "DATETIME",
        'is_approved':      "TINYINT(1) DEFAULT 1",
        'comments_count':   "INTEGER DEFAULT 0",
        'contributor_name': "VARCHAR(255)",
        'ip_address':       "VARCHAR(45)",
        'created_by':       "INT UNSIGNED",
        'updated_by':       "INT UNSIGNED",
        'approved_by':      "INT UNSIGNED"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to dreams table.")
            cursor.execute(f"ALTER TABLE dreams ADD COLUMN {col_name} {col_def}")

    # Note about created_by / updated_by:
    # These columns were already created in the CREATE TABLE above.
    # They allow the public dreams page to display "Created by: [Name]".
    # If you see "Unknown" on old dreams, it is only because created_by was NULL.

    # Indexes for dreams (safe — will not fail if they already exist)
    try:
        cursor.execute("CREATE INDEX idx_dreams_visibility ON dreams(visibility)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_dreams_approved ON dreams(is_approved)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_dreams_user ON dreams(user_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_dreams_date_posted ON dreams(date_posted DESC)")
    except: pass

    # ------------------------------------------------------------------
    # ----- DREAM_COMMENTS TABLE (with parent_id for replies) -----
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dream_comments (
            id               INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            dream_id         INT UNSIGNED NOT NULL,
            comment          TEXT NOT NULL,
            date_posted      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id          INT UNSIGNED,
            contributor_name VARCHAR(255),
            ip_address       VARCHAR(45),
            parent_id        INT UNSIGNED NULL,   -- for simple one-level replies
            FOREIGN KEY(dream_id) REFERENCES dreams(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id)   REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(parent_id) REFERENCES dream_comments(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'dream_comments'
    """)
    existing_comments_columns = [row[0] for row in cursor.fetchall()]

    # Safe addition of parent_id if missing
    if 'parent_id' not in existing_comments_columns:
        print("Migration: Adding missing 'parent_id' column to dream_comments for one-level replies")
        cursor.execute("""
            ALTER TABLE dream_comments 
            ADD COLUMN parent_id INT UNSIGNED NULL AFTER ip_address,
            ADD FOREIGN KEY (parent_id) REFERENCES dream_comments(id) ON DELETE CASCADE
        """)

    columns_to_add_comments = {
        'contributor_name': "VARCHAR(255)",
        'ip_address':       "VARCHAR(45)"
    }

    for col_name, col_def in columns_to_add_comments.items():
        if col_name not in existing_comments_columns:
            print(f"Migration: Adding missing column '{col_name}' to dream_comments table.")
            cursor.execute(f"ALTER TABLE dream_comments ADD COLUMN {col_name} {col_def}")

    # Indexes for dream_comments
    try:
        cursor.execute("CREATE INDEX idx_dream_comments_dream ON dream_comments(dream_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_dream_comments_date ON dream_comments(date_posted DESC)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_dream_comments_parent ON dream_comments(parent_id)")
    except: pass

