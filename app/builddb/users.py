# myvinechurchonline/app/builddb/users.py
# Full path: myvinechurchonline/app/builddb/users.py
# File name: users.py
# Brief, detailed purpose: Creates and synchronizes the users table for MariaDB.
# Definitive schema including new privacy preference columns and secure check-in PIN:
#   - allow_proxy_checkin TINYINT(1) DEFAULT 1 - allow others to check in for attendance.
#   - allow_group_add TINYINT(1) DEFAULT 1 - allow staff to add to groups.
#   - allow_family_search TINYINT(1) DEFAULT 1 - allow appearing in family searches.
#   - checkin_pin TEXT - hashed PIN for kiosk self check-in (hashed with Werkzeug, not plain).
# All original fields preserved + safe migration pattern.
# MariaDB-compatible syntax (INT UNSIGNED, ENGINE=InnoDB, proper AUTO_INCREMENT).

def create_tables(cursor):
    """
    Creates/updates the users table in MariaDB.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- USERS TABLE (MariaDB) -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                          INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            username                    TEXT UNIQUE NOT NULL,
            password                    TEXT NOT NULL,
            first_name                  TEXT,
            last_name                   TEXT,
            email                       TEXT UNIQUE,
            phone                       TEXT,
            address                     TEXT,
            birthday                    DATE,
            show_birthday               INTEGER DEFAULT 1,
            role                        TEXT DEFAULT 'Member',
            needs_approval              INTEGER DEFAULT 1,
            approved_by                 INT UNSIGNED,
            created_by                  INT UNSIGNED,
            accepts_emails              INTEGER DEFAULT 1,
            accepts_event_emails        INTEGER DEFAULT 1,
            accepts_donation_emails     INTEGER DEFAULT 1,
            accepts_announcement_emails INTEGER DEFAULT 1,
            accepts_prayer_emails       INTEGER DEFAULT 1,
            accepts_group_emails        INTEGER DEFAULT 1,
            accepts_newsletter_emails   INTEGER DEFAULT 1,
            accepts_volunteer_emails    INTEGER DEFAULT 1,
            accepts_bill_emails         INTEGER DEFAULT 1,
            allow_proxy_checkin         TINYINT(1) DEFAULT 1,
            allow_group_add             TINYINT(1) DEFAULT 1,
            allow_family_search         TINYINT(1) DEFAULT 1,
            checkin_pin                 TEXT,                      -- Hashed PIN for kiosk self check-in (NULL = no PIN)
            created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (approved_by)   REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by)    REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'username':                    "TEXT UNIQUE NOT NULL",
        'password':                    "TEXT NOT NULL",
        'first_name':                  "TEXT",
        'last_name':                   "TEXT",
        'email':                       "TEXT UNIQUE",
        'phone':                       "TEXT",
        'address':                     "TEXT",
        'birthday':                    "DATE",
        'show_birthday':               "INTEGER DEFAULT 1",
        'role':                        "TEXT DEFAULT 'Member'",
        'needs_approval':              "INTEGER DEFAULT 1",
        'approved_by':                 "INT UNSIGNED",
        'created_by':                  "INT UNSIGNED",
        'accepts_emails':              "INTEGER DEFAULT 1",
        'accepts_event_emails':        "INTEGER DEFAULT 1",
        'accepts_donation_emails':     "INTEGER DEFAULT 1",
        'accepts_announcement_emails': "INTEGER DEFAULT 1",
        'accepts_prayer_emails':       "INTEGER DEFAULT 1",
        'accepts_group_emails':        "INTEGER DEFAULT 1",
        'accepts_newsletter_emails':   "INTEGER DEFAULT 1",
        'accepts_volunteer_emails':    "INTEGER DEFAULT 1",
        'allow_proxy_checkin':         "TINYINT(1) DEFAULT 1",
        'allow_group_add':             "TINYINT(1) DEFAULT 1",
        'allow_family_search':         "TINYINT(1) DEFAULT 1",
        'checkin_pin':                 "TEXT",
        'email_verified':              "TINYINT(1) DEFAULT 0",
        'email_verification_token':    "VARCHAR(128)",
        'email_verified_at':           "TIMESTAMP NULL",
        'approved_at':                 "TIMESTAMP NULL",
        'totp_secret':                 "TEXT",
        'totp_enabled':                "TINYINT(1) DEFAULT 0",
        'notify_new_registrations':    "TINYINT(1) DEFAULT 0",
        'accepts_bill_emails':         "INTEGER DEFAULT 1",
        'accepts_worship_emails':      "INTEGER DEFAULT 1",
        'is_shadow_banned':            "TINYINT(1) DEFAULT 0",
        'shadow_banned_at':            "TIMESTAMP NULL",
        'shadow_banned_by':            "INT UNSIGNED NULL",
        'login_locked_until':          "DATETIME NULL",
        'login_locked_by':             "INT UNSIGNED NULL",
        'created_at':                  "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'updated_at':                  "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to users table.")
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

    # Add foreign keys if they don't exist
    try:
        cursor.execute("ALTER TABLE users ADD CONSTRAINT fk_users_approved_by FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD CONSTRAINT fk_users_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL")
    except:
        pass

    # Indexes for common operations
    try:
        cursor.execute("CREATE INDEX idx_users_username ON users(username(255))")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX idx_users_email ON users(email(255))")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX idx_users_role ON users(role(50))")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX idx_users_needs_approval ON users(needs_approval)")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX idx_users_created ON users(created_at DESC)")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX idx_users_created_by ON users(created_by)")
    except:
        pass

