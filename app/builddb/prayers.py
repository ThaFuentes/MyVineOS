# MYVINECHURCH.ONLINE/app/builddb/prayers.py
# Full path: MYVINECHURCH.ONLINE/app/builddb/prayers.py
# File name: prayers.py
# Brief, detailed purpose: Creates/updates the prayers and prayers_added tables for MariaDB.
# This is the 100% complete rebuild — every single column, table, index, migration step, and behavior is preserved exactly as you had it.
# The only updates are: much clearer comments.html, better code organization, and explicit support for created_by / updated_by (this powers "Created by: [Name]" on the public prayers page, just like events, announcements, and dreams).
# No new tables, no behavior changes.

def create_tables(cursor):
    """
    Creates/updates the prayers and prayers_added tables.
    Designed for both fresh DB creation and safe migration of existing databases.
    The created_by column is required for displaying WHO created each prayer request on the public page.
    """

    # ------------------------------------------------------------------
    # ----- PRAYERS TABLE -----
    # ------------------------------------------------------------------
    # This table stores every prayer request.
    # created_by and updated_by are used to show "Created by: [Username]"
    # on the public prayers listing (exactly like events/announcements/dreams).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prayers (
            id               INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            title            VARCHAR(255) NOT NULL,
            description      TEXT NOT NULL,
            date_posted      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visibility       VARCHAR(20) NOT NULL DEFAULT 'public'
                             CHECK(visibility IN ('public', 'private')),
            user_id          INT UNSIGNED,
            created_by       INT UNSIGNED,           -- ← This column shows WHO created the prayer request
            updated_by       INT UNSIGNED,
            contributor_name VARCHAR(255),           -- For non-registered users
            ip_address       VARCHAR(45),            -- For IP tracking/banning (IPv6 safe)
            FOREIGN KEY(user_id)    REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(updated_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # ------------------------------------------------------------------
    # Safe column additions / migration for prayers table
    # ------------------------------------------------------------------
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prayers'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'visibility':       "VARCHAR(20) NOT NULL DEFAULT 'public' CHECK(visibility IN ('public', 'private'))",
        'contributor_name': "VARCHAR(255)",
        'ip_address':       "VARCHAR(45)",
        'user_id':          "INT UNSIGNED",
        'created_by':       "INT UNSIGNED",
        'updated_by':       "INT UNSIGNED",
        'status':           "VARCHAR(20) NOT NULL DEFAULT 'approved'",
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to prayers table.")
            cursor.execute(f"ALTER TABLE prayers ADD COLUMN {col_name} {col_def}")

    # Note about created_by / updated_by:
    # These columns were added (or already existed) in the CREATE TABLE above.
    # They allow the public prayers page to display "Created by: [Name]".
    # If you see "Unknown" on old prayers, it is only because created_by was NULL.

    # Indexes for prayers (safe — will not fail if they already exist)
    try:
        cursor.execute("CREATE INDEX idx_prayers_visibility ON prayers(visibility)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prayers_user ON prayers(user_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prayers_date ON prayers(date_posted DESC)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prayers_status ON prayers(status)")
    except: pass

    # Backfill status for any legacy rows
    try:
        cursor.execute("UPDATE prayers SET status = 'approved' WHERE status IS NULL OR status = ''")
    except: pass

    # ------------------------------------------------------------------
    # ----- PRAYERS_ADDED TABLE (responses / added prayers) -----
    # ------------------------------------------------------------------
    # This table stores replies to prayer requests (with simple one-level replies via parent_id).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prayers_added (
            id                 INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            prayer_request_id  INT UNSIGNED NOT NULL,
            prayer             TEXT NOT NULL,
            date_added         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id            INT UNSIGNED,
            contributor_name   VARCHAR(255),
            ip_address         VARCHAR(45),
            parent_id          INT UNSIGNED NULL,   -- for simple one-level replies only
            FOREIGN KEY(prayer_request_id) REFERENCES prayers(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id)           REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(parent_id)         REFERENCES prayers_added(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for prayers_added table
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prayers_added'
    """)
    existing_added_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add_responses = {
        'contributor_name': "VARCHAR(255)",
        'ip_address':       "VARCHAR(45)",
        'user_id':          "INT UNSIGNED",
        'parent_id':        "INT UNSIGNED NULL"
    }

    for col_name, col_def in columns_to_add_responses.items():
        if col_name not in existing_added_columns:
            print(f"Migration: Adding missing column '{col_name}' to prayers_added table.")
            cursor.execute(f"ALTER TABLE prayers_added ADD COLUMN {col_name} {col_def}")

    # Indexes for prayers_added
    try:
        cursor.execute("CREATE INDEX idx_prayers_added_request ON prayers_added(prayer_request_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prayers_added_date ON prayers_added(date_added DESC)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_prayers_added_parent ON prayers_added(parent_id)")
    except: pass

    print(" prayers.py migration completed successfully (including prayers_added table with parent_id for simple one-level replies)")