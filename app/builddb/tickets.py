# myvinechurchonline/app/builddb/tickets.py
# Full path: myvinechurchonline/app/builddb/tickets.py
# File name: tickets.py
# Brief, detailed purpose: Creates/updates the ticket_categories, ticket_managers, tickets, and ticket_comments tables for MariaDB.
# Supports guest submissions (contact_name, contact_email, ip_address) in allowed categories.
# Dedicated ticket_managers junction table for explicit management permission (no role auto-access).
# Priority and status tracking.
# Safe schema evolution using INFORMATION_SCHEMA.COLUMNS.
# Isolated module – called from builddb.py during DB initialization.
# All ID/FK columns use UNSIGNED INT.
# FULL REBUILD: Added missing ticket_managers table, consistent %s placeholders for MariaDB/PyMySQL,
# improved migration safety, default categories with realistic church use cases.

def create_tables(cursor):
    """
    Creates/updates the tickets-related tables.
    Designed for both fresh DB creation and safe migration of existing databases.
    Order: categories → managers → tickets → comments.html (to satisfy FK constraints).
    """

    # ----- TICKET_CATEGORIES TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_categories (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(255) NOT NULL UNIQUE,
            description TEXT,
            allow_guest_creation TINYINT(1) DEFAULT 0,
            default_priority VARCHAR(20) DEFAULT 'medium' 
                             CHECK(default_priority IN ('low', 'medium', 'high', 'urgent')),
            sort_order INT UNSIGNED DEFAULT 99
        ) ENGINE=InnoDB;
    """)

    # Safe column additions
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ticket_categories'
    """)
    existing_cols = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'description': "TEXT",
        'allow_guest_creation': "TINYINT(1) DEFAULT 0",
        'default_priority': "VARCHAR(20) DEFAULT 'medium' CHECK(default_priority IN ('low', 'medium', 'high', 'urgent'))",
        'sort_order': "INT UNSIGNED DEFAULT 99"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_cols:
            print(f"Migration: Adding missing column '{col_name}' to ticket_categories table.")
            cursor.execute(f"ALTER TABLE ticket_categories ADD COLUMN {col_name} {col_def}")

    # Indexes
    try:
        cursor.execute("CREATE INDEX idx_categories_sort ON ticket_categories(sort_order)")
    except:
        pass

    # Default church-relevant categories (INSERT IGNORE for idempotency)
    default_categories = [
        ('Membership', 'New member applications, profile updates, family linking', 1, 'medium', 10),
        ('Building/Property', 'Maintenance, repairs, plumbing, cleaning, facility requests', 1, 'high', 20),
        ('Website', 'Content updates, broken links, feature requests for myvinechurch.online', 1, 'medium', 30),
        ('Audio/Visual', 'Sound system, projectors, live stream issues', 0, 'high', 40),
        ('Events', 'Event setup, potluck coordination, registration problems', 1, 'medium', 50),
        ('Finance/Donations', 'Donation questions, statement requests', 0, 'medium', 60),
        ('IT/Support', 'Computer, software, app issues for staff', 0, 'medium', 70),
        ('General', 'Anything else', 1, 'low', 99)
    ]

    for name, desc, guest, pri, order in default_categories:
        cursor.execute("""
            INSERT IGNORE INTO ticket_categories 
            (name, description, allow_guest_creation, default_priority, sort_order)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, desc, guest, pri, order))

    # ----- TICKET_MANAGERS TABLE (junction – explicit management permission) -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_managers (
            user_id INT UNSIGNED PRIMARY KEY,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assigned_by INT UNSIGNED,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(assigned_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # Safe column additions (in case of future expansion)
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ticket_managers'
    """)
    existing_manager_cols = [row[0] for row in cursor.fetchall()]

    manager_columns_to_add = {
        'assigned_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'assigned_by': "INT UNSIGNED"
    }

    for col_name, col_def in manager_columns_to_add.items():
        if col_name not in existing_manager_cols:
            print(f"Migration: Adding missing column '{col_name}' to ticket_managers table.")
            cursor.execute(f"ALTER TABLE ticket_managers ADD COLUMN {col_name} {col_def}")

    # Index
    try:
        cursor.execute("CREATE INDEX idx_managers_user ON ticket_managers(user_id)")
    except:
        pass

    # ----- TICKETS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            category_id INT UNSIGNED NOT NULL,
            priority VARCHAR(20) DEFAULT 'medium' 
                     CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
            status VARCHAR(20) DEFAULT 'open' 
                   CHECK(status IN ('open', 'in_progress', 'resolved', 'closed')),
            created_by INT UNSIGNED,
            contact_name VARCHAR(255),
            contact_email VARCHAR(255),
            ip_address VARCHAR(45),
            assigned_to INT UNSIGNED,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY(category_id) REFERENCES ticket_categories(id) ON DELETE RESTRICT,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(assigned_to) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    # Safe column additions
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tickets'
    """)
    existing_ticket_cols = [row[0] for row in cursor.fetchall()]

    ticket_columns_to_add = {
        'priority': "VARCHAR(20) DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent'))",
        'status': "VARCHAR(20) DEFAULT 'open' CHECK(status IN ('open', 'in_progress', 'resolved', 'closed'))",
        'contact_name': "VARCHAR(255)",
        'contact_email': "VARCHAR(255)",
        'ip_address': "VARCHAR(45)",
        'assigned_to': "INT UNSIGNED",
        'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
    }

    for col_name, col_def in ticket_columns_to_add.items():
        if col_name not in existing_ticket_cols:
            print(f"Migration: Adding missing column '{col_name}' to tickets table.")
            cursor.execute(f"ALTER TABLE tickets ADD COLUMN {col_name} {col_def}")

    # Indexes
    try:
        cursor.execute("CREATE INDEX idx_tickets_status ON tickets(status)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_tickets_category ON tickets(category_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_tickets_priority ON tickets(priority)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_tickets_assigned ON tickets(assigned_to)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_tickets_created_by ON tickets(created_by)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_tickets_updated ON tickets(updated_at DESC)")
    except: pass

    # ----- TICKET_COMMENTS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_comments (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            ticket_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            comment TEXT NOT NULL,
            notify_creator TINYINT(1) DEFAULT 1,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    # Safe column additions
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ticket_comments'
    """)
    existing_comment_cols = [row[0] for row in cursor.fetchall()]

    if 'notify_creator' not in existing_comment_cols:
        print("Migration: Adding missing column 'notify_creator' to ticket_comments table.")
        cursor.execute("ALTER TABLE ticket_comments ADD COLUMN notify_creator TINYINT(1) DEFAULT 1")

    # Indexes
    try:
        cursor.execute("CREATE INDEX idx_comments_ticket ON ticket_comments(ticket_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_comments_date ON ticket_comments(date_added DESC)")
    except: pass