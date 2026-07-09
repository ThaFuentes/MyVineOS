# myvinechurchonline/app/builddb/donations.py
# Full path: myvinechurchonline/app/builddb/donations.py
# File name: donations.py
# Brief, detailed purpose: Creates the donations table for MariaDB.
# Tracks donation records (name, amount, date, method, notes) with additional columns for receipt compliance:
# confirmation_number (TEXT) and goods_services_provided (INTEGER flag).
# No user_id foreign key in this table (donations may be recorded anonymously or linked separately).
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module – called from builddb.py during DB initialization.

def create_tables(cursor):
    """
    Creates/updates the donations table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- DONATIONS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id                       INT PRIMARY KEY AUTO_INCREMENT,
            name                     TEXT NOT NULL,
            amount                   REAL NOT NULL,
            date                     TEXT NOT NULL,                -- Stored as 'YYYY-MM-DD' string
            method                   TEXT NOT NULL,
            notes                    TEXT,
            confirmation_number      TEXT,
            goods_services_provided  INTEGER DEFAULT 0
        );
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'donations'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'notes':                    "TEXT",
        'confirmation_number':      "TEXT",
        'goods_services_provided':  "INTEGER DEFAULT 0",
        'user_id':                  "INT NULL",
        'donor_email':              "TEXT",
        'donor_phone':              "TEXT",
        'donor_type':               "TEXT DEFAULT 'guest'",
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to donations table.")
            cursor.execute(f"ALTER TABLE donations ADD COLUMN {col_name} {col_def}")

    # Indexes for common queries (listings, reports, sorting)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_date ON donations(date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_amount ON donations(amount DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_name ON donations(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_user_id ON donations(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_donations_donor_type ON donations(donor_type)")