# app/builddb/recurring_bills.py
# Full path: WebChurchMan/app/builddb/recurring_bills.py
# File name: recurring_bills.py
# Brief, detailed purpose: Creates/updates the recurring_bills, recurring_bill_assignments,
# and bill_payment_history tables for MariaDB.

def create_tables(cursor):
    """
    Creates/updates the recurring bills-related tables.
    Designed for both fresh DB creation and safe migration of existing databases.
    Resolved Errno 150 by ensuring created_by is NULLABLE to support ON DELETE SET NULL.
    """

    # ----- RECURRING_BILLS TABLE -----
    # Note: created_by is NULLABLE because the FK action is ON DELETE SET NULL.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_bills (
            id                  INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            bill_name           VARCHAR(255) NOT NULL,
            vendor_name         VARCHAR(255),
            description         TEXT,
            typical_amount      DECIMAL(10,2),
            account_number      VARCHAR(255),
            customer_number     VARCHAR(255),
            phone1              VARCHAR(50),
            phone2              VARCHAR(50),
            address             TEXT,
            payment_url         VARCHAR(512),
            login_url           VARCHAR(512),
            additional_links    TEXT,                        -- JSON array of {"label": "...", "url": "..."}
            encrypted_username  BLOB,                        -- Fernet-encrypted
            encrypted_password  BLOB,                        -- Fernet-encrypted
            frequency           VARCHAR(20) NOT NULL DEFAULT 'monthly'
                                CHECK(frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly')),
            due_day             TINYINT UNSIGNED,
            due_month           TINYINT UNSIGNED,
            reminder_days_before TINYINT UNSIGNED DEFAULT 7,
            next_due_date       DATE,
            last_reminder_sent  DATETIME,
            current_status      VARCHAR(20) DEFAULT 'pending'
                                CHECK(current_status IN ('pending', 'paid', 'overdue', 'partial')),
            notes               TEXT,
            created_by          INT UNSIGNED,                -- Fix: Removed NOT NULL to match SET NULL action
            updated_by          INT UNSIGNED,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(updated_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # Safe column additions (using direct query to avoid formatting issues)
    query = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recurring_bills'"
    cursor.execute(query)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'vendor_name':            "VARCHAR(255)",
        'description':            "TEXT",
        'typical_amount':         "DECIMAL(10,2)",
        'account_number':         "VARCHAR(255)",
        'customer_number':        "VARCHAR(255)",
        'phone1':                 "VARCHAR(50)",
        'phone2':                 "VARCHAR(50)",
        'address':                "TEXT",
        'payment_url':            "VARCHAR(512)",
        'login_url':              "VARCHAR(512)",
        'additional_links':       "TEXT",
        'encrypted_username':     "BLOB",
        'encrypted_password':     "BLOB",
        'frequency':              "VARCHAR(20) NOT NULL DEFAULT 'monthly' CHECK(frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly'))",
        'due_day':                "TINYINT UNSIGNED",
        'due_month':              "TINYINT UNSIGNED",
        'reminder_days_before':   "TINYINT UNSIGNED DEFAULT 7",
        'next_due_date':          "DATE",
        'last_reminder_sent':     "DATETIME",
        'current_status':         "VARCHAR(20) DEFAULT 'pending' CHECK(current_status IN ('pending', 'paid', 'overdue', 'partial'))",
        'notes':                  "TEXT",
        'updated_by':             "INT UNSIGNED",
        'updated_at':             "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
        'reminder_email':         "VARCHAR(512)",
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to recurring_bills table.")
            cursor.execute(f"ALTER TABLE recurring_bills ADD COLUMN {col_name} {col_def}")

    # Indexes
    try:
        cursor.execute("CREATE INDEX idx_recurring_bills_next_due ON recurring_bills(next_due_date)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_recurring_bills_frequency ON recurring_bills(frequency)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_recurring_bills_status ON recurring_bills(current_status)")
    except: pass

    # ----- RECURRING_BILL_ASSIGNMENTS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_bill_assignments (
            id         INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            bill_id    INT UNSIGNED NOT NULL,
            user_id    INT UNSIGNED NOT NULL,
            remind_me  TINYINT(1) DEFAULT 1,
            FOREIGN KEY(bill_id) REFERENCES recurring_bills(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE KEY uniq_bill_user (bill_id, user_id)
        ) ENGINE=InnoDB;
    """)

    query_assign = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recurring_bill_assignments'"
    cursor.execute(query_assign)
    existing_assign = [row[0] for row in cursor.fetchall()]

    if 'remind_me' not in existing_assign:
        print("Migration: Adding missing column 'remind_me' to recurring_bill_assignments table.")
        cursor.execute("ALTER TABLE recurring_bill_assignments ADD COLUMN remind_me TINYINT(1) DEFAULT 1")

    try:
        cursor.execute("CREATE INDEX idx_assignments_user ON recurring_bill_assignments(user_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_assignments_bill ON recurring_bill_assignments(bill_id)")
    except: pass

    # ----- BILL_PAYMENT_HISTORY TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bill_payment_history (
            id            INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            bill_id       INT UNSIGNED NOT NULL,
            payment_date  DATE NOT NULL,
            amount        DECIMAL(10,2) NOT NULL,
            paid_by       INT UNSIGNED,
            notes         TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(bill_id) REFERENCES recurring_bills(id) ON DELETE CASCADE,
            FOREIGN KEY(paid_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    try:
        cursor.execute("CREATE INDEX idx_payment_bill ON bill_payment_history(bill_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_payment_date ON bill_payment_history(payment_date DESC)")
    except: pass