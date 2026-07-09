# myvinechurchonline/app/builddb/email_settings.py
# Full path: myvinechurchonline/app/builddb/email_settings.py
# File name: email_settings.py
# Brief, detailed purpose: Creates the app_email_settings and church_email_settings tables for MariaDB.
# Stores encrypted SMTP/email configuration (server, port, credentials, mode) separately for app-wide and church-specific settings.
# No foreign keys; independent tables.
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module – called from builddb.py during DB initialization.

def create_tables(cursor):
    """
    Creates/updates the email settings tables.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- APP_EMAIL_SETTINGS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_email_settings (
            id             INT PRIMARY KEY AUTO_INCREMENT,
            app_name       TEXT NOT NULL,
            email_server   TEXT,
            email_port     INT,
            smtp_server    TEXT,
            smtp_port      INT,
            email_mode     TEXT,
            email_address  TEXT,
            email_password TEXT                        -- Encrypted in application logic
        );
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'app_email_settings'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add_app = {
        'app_name':       "TEXT NOT NULL",
        'email_server':   "TEXT",
        'email_port':     "INT",
        'smtp_server':    "TEXT",
        'smtp_port':      "INT",
        'email_mode':     "TEXT",
        'email_address':  "TEXT",
        'email_password': "TEXT"
    }

    for col_name, col_def in columns_to_add_app.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to app_email_settings table.")
            cursor.execute(f"ALTER TABLE app_email_settings ADD COLUMN {col_name} {col_def}")

    # ----- CHURCH_EMAIL_SETTINGS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS church_email_settings (
            id             INT PRIMARY KEY AUTO_INCREMENT,
            church_name    TEXT NOT NULL,
            email_server   TEXT,
            email_port     INT,
            smtp_server    TEXT,
            smtp_port      INT,
            email_mode     TEXT,
            email_address  TEXT,
            email_password TEXT                        -- Encrypted in application logic
        );
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'church_email_settings'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add_church = {
        'church_name':    "TEXT NOT NULL",
        'email_server':   "TEXT",
        'email_port':     "INT",
        'smtp_server':    "TEXT",
        'smtp_port':      "INT",
        'email_mode':     "TEXT",
        'email_address':  "TEXT",
        'email_password': "TEXT"
    }

    for col_name, col_def in columns_to_add_church.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to church_email_settings table.")
            cursor.execute(f"ALTER TABLE church_email_settings ADD COLUMN {col_name} {col_def}")