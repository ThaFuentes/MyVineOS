# app/builddb/family_relations.py
# Full path: WebChurchMan/app/builddb/family_relations.py
# File name: family_relations.py
# Brief, detailed purpose: Creates and safely migrates the family_relations table.
#   Manages bidirectional family relationships between users with:
#     - relation_type (spouse, parent, child, sibling, etc.)
#     - status (pending → approved/rejected)
#     - timestamps for request and response
#     - optional admin override field (approved_by)
#   Enforces uniqueness per user pair (prevents duplicate requests in either direction).
#   Uses INT UNSIGNED for all FKs to match users.id and prevent errno 150 issues.
#   Safe schema evolution: checks existing columns via INFORMATION_SCHEMA and adds missing ones.
#   Idempotent indexes and CHECK constraints.
#   Isolated module – called from builddb.py or scripts/init_db.py during DB initialization.
#   Fully compatible with models/user.py family functions.

def create_tables(cursor):
    """
    Creates/updates the family_relations table.
    Safe for fresh databases and existing ones (adds missing columns/constraints).
    """

    print("Starting family_relations table setup...")

    # ----- FAMILY_RELATIONS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS family_relations (
            id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            user_id       INT UNSIGNED NOT NULL,
            relative_id   INT UNSIGNED NOT NULL,
            relation_type VARCHAR(50) NOT NULL,
            status        VARCHAR(20) NOT NULL DEFAULT 'pending',
            requested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            responded_at  DATETIME DEFAULT NULL,
            approved_by   INT UNSIGNED DEFAULT NULL,
            FOREIGN KEY (user_id)     REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (relative_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE KEY uniq_pair (user_id, relative_id),
            CONSTRAINT chk_relation_type CHECK (
                relation_type IN ('spouse', 'parent', 'child', 'sibling')
            ),
            CONSTRAINT chk_status CHECK (
                status IN ('pending', 'approved', 'rejected')
            )
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # Safe column additions for migration / older schema versions
    cursor.execute("""
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
          AND TABLE_NAME = 'family_relations'
    """)
    existing = {row[0] for row in cursor.fetchall()}

    # Define columns we want to ensure exist (with full definition)
    columns_to_ensure = {
        'relation_type':  "VARCHAR(50) NOT NULL",
        'status':         "VARCHAR(20) NOT NULL DEFAULT 'pending'",
        'requested_at':   "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'responded_at':   "DATETIME DEFAULT NULL",
        'approved_by':    "INT UNSIGNED DEFAULT NULL"
    }

    for col, definition in columns_to_ensure.items():
        if col not in existing:
            print(f"  Migration: Adding column '{col}' to family_relations")
            cursor.execute(f"ALTER TABLE family_relations ADD COLUMN {col} {definition}")

    # Idempotent CHECK constraints (MariaDB allows IF NOT EXISTS in some versions; wrapped safely)
    safe_exec(cursor, """
        ALTER TABLE family_relations 
        ADD CONSTRAINT IF NOT EXISTS chk_relation_type 
        CHECK (relation_type IN ('spouse', 'parent', 'child', 'sibling'))
    """)

    safe_exec(cursor, """
        ALTER TABLE family_relations 
        ADD CONSTRAINT IF NOT EXISTS chk_status 
        CHECK (status IN ('pending', 'approved', 'rejected'))
    """)

    # Idempotent indexes for performance
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_family_user ON family_relations(user_id)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_family_relative ON family_relations(relative_id)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_family_status ON family_relations(status)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_family_requested ON family_relations(requested_at DESC)")

    print("family_relations table setup complete.\n")


# Helper – silently ignore duplicate/already-exists errors during ALTER/INDEX
def safe_exec(cursor, sql):
    try:
        cursor.execute(sql)
    except Exception as e:
        err_str = str(e).lower()
        if "duplicate" not in err_str and "already exists" not in err_str:
            print(f"    Warning during constraint/index: {e}")