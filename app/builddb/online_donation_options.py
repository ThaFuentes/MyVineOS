# myvinechurchonline/app/builddb/online_donation_options.py
# Full path: myvinechurchonline/app/builddb/online_donation_options.py
# File name: online_donation_options.py
# Brief, detailed purpose: Creates the online_donation_options table.
# Stores multiple configurable giving methods (Stripe link, PayPal embed, Venmo, QR code, etc.).
# Each row is one public giving option (repeater in Settings UI).
# Safe schema evolution: creates table if missing, adds columns safely.
# Isolated module – called from builddb.py during DB initialization (after old_settings.py).
# FIXED FOR MARIADB: Uses MySQL/MariaDB-compatible AUTO_INCREMENT syntax (no SQLite "INTEGER PRIMARY KEY AUTOINCREMENT").

def create_tables(cursor):
    """
    Creates/updates the online_donation_options table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- ONLINE DONATION OPTIONS TABLE (MariaDB-compatible) -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS online_donation_options (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            name            TEXT NOT NULL,
            option_type     TEXT,
            url             TEXT,
            embed_code      TEXT,
            image_path      TEXT,
            sort_order      INT DEFAULT 0,
            enabled         TINYINT DEFAULT 1
        )
    """)

    # Index for efficient public page loading
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_online_options_sort 
        ON online_donation_options(sort_order, enabled)
    """)

    # Safe column additions (in case of future expansions)
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'online_donation_options'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'name':        "TEXT NOT NULL",
        'option_type': "TEXT",
        'url':         "TEXT",
        'embed_code':  "TEXT",
        'image_path':  "TEXT",
        'sort_order':  "INT DEFAULT 0",
        'enabled':     "TINYINT DEFAULT 1"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to online_donation_options table.")
            cursor.execute(f"ALTER TABLE online_donation_options ADD COLUMN {col_name} {col_def}")