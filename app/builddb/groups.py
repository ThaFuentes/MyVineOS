# myvinechurchonline/app/builddb/groups.py
# Full path: myvinechurchonline/app/builddb/groups.py
# File name: groups.py
# Brief, detailed purpose: Creates/updates the groups table and seeds essential system groups for MariaDB in the MYVINECHURCH.ONLINE rebuild (2026).
# Supports group name (unique), description, visibility (public/private), permissions (JSON stored as TEXT),
# full audit trail (created_by/updated_by + timestamps).
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module - called from builddb.py during DB initialization.
# FULL REBUILD: Expanded seeding to include all new Ticket groups (Ticket IT Group, Ticket Maintenance Group,
# Ticket Memberships Group, Ticket General Group). Ticket Managers description updated for new design.
# Pastoral Group and Worship Team Group left completely untouched as requested.

def create_tables(cursor):
    """
    Creates/updates the groups table and seeds essential system groups.
    Designed for both fresh DB creation and safe migration of existing databases.
    """
    # ----- GROUPS TABLE -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(255) NOT NULL UNIQUE,
            description TEXT,
            visibility VARCHAR(20) NOT NULL DEFAULT 'private'
                        CHECK(visibility IN ('public', 'private')),
            permissions TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_by INT UNSIGNED,
            updated_by INT UNSIGNED,
            FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
            FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)
    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'groups'
    """)
    existing_cols = [row[0] for row in cursor.fetchall()]
    columns_to_add = {
        'description': "TEXT",
        'visibility': "VARCHAR(20) NOT NULL DEFAULT 'private' CHECK(visibility IN ('public', 'private'))",
        'permissions': "TEXT NOT NULL DEFAULT '[]'",
        'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
        'created_by': "INT UNSIGNED",
        'updated_by': "INT UNSIGNED",
        'system_key': "VARCHAR(64) NULL"
    }
    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_cols:
            print(f"Migration: Adding missing column '{col_name}' to groups table.")
            cursor.execute(f"ALTER TABLE groups ADD COLUMN {col_name} {col_def}")
    # Indexes for common queries
    try:
        cursor.execute("CREATE INDEX idx_groups_visibility ON groups(visibility)")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX idx_groups_created ON groups(created_at DESC)")
    except:
        pass
    try:
        cursor.execute("CREATE UNIQUE INDEX idx_groups_system_key ON groups(system_key)")
    except:
        pass

    # ----- SEED ESSENTIAL SYSTEM GROUPS -----
    # Using INSERT IGNORE - safe to run repeatedly (name is UNIQUE).
    # All new Ticket groups added here. Pastoral and Worship left untouched.
    essential_groups = [
        (
            "Ticket Managers",
            "Dedicated group for users who can fully manage the support ticket/helpdesk system (see ALL tickets, assign to anyone, full stats).",
            "private",
            '[]'   # We now use group name matching instead of permissions JSON
        ),
        (
            "Ticket IT Group",
            "Handles all IT/Support tickets (computers, software, app issues). Members see and manage only IT tickets.",
            "private",
            '[]'
        ),
        (
            "Ticket Maintenance Group",
            "Handles all Building/Property tickets (repairs, cleaning, facility requests). Members see and manage only maintenance tickets.",
            "private",
            '[]'
        ),
        (
            "Ticket Memberships Group",
            "Handles all Membership tickets (new members, profile updates, family linking). Members see and manage only membership tickets.",
            "private",
            '[]'
        ),
        (
            "Ticket General Group",
            "Basic/limited group for volunteers. Can see unassigned General tickets and their own assigned tickets only. Cannot assign to others.",
            "private",
            '[]'
        ),
        (
            "Pastoral Group",
            "Highly sensitive group for pastoral care, counseling notes, and leadership oversight.",
            "private",
            '["view_pastoral_notes", "manage_membership", "access_sensitive_data"]'
        ),
        (
            "Worship Team Group",
            "Planning for services, song lists, and team rehearsals.",
            "private",
            '["view_setlists", "upload_chord_charts", "manage_rehearsals"]'
        ),
        (
            "Gathering Place Managers",
            "Protected system group - access to The Gathering Place Manager (site-wide content moderation). "
            "Only the Owner may add members; Admins already in this group may also add members. "
            "Regular group members cannot add others.",
            "private",
            '["moderate_announcements", "moderate_events", "moderate_sermons", "moderate_prayers", "moderate_dreams", "moderate_prophecies"]'
        ),
    ]
    for name, desc, visibility, perms in essential_groups:
        cursor.execute("""
            INSERT IGNORE INTO groups (name, description, visibility, permissions)
            VALUES (%s, %s, %s, %s)
        """, (name, desc, visibility, perms))
    print("Groups seeded/updated (if not already present): Ticket Managers, Ticket IT Group, Ticket Maintenance Group, Ticket Memberships Group, Ticket General Group, Pastoral Group, Worship Team Group, Gathering Place Managers.")

    # Stable system identifier - survives group renames in the UI
    try:
        cursor.execute("""
            UPDATE groups SET system_key = 'gathering_place'
            WHERE name = %s AND (system_key IS NULL OR system_key = '')
        """, ("Gathering Place Managers",))
        cursor.execute("""
            UPDATE groups SET system_key = 'gathering_place'
            WHERE system_key IS NULL AND description LIKE %s
        """, ('%Protected system group - access to The Gathering Place Manager%',))
    except Exception as e:
        print(f"Gathering Place system_key note: {e}")

    # Ensure Owner is in Gathering Place Managers (Owner always has access; membership keeps roster accurate)
    try:
        cursor.execute("SELECT id FROM groups WHERE system_key = 'gathering_place' LIMIT 1")
        gp_row = cursor.fetchone()
        if not gp_row:
            cursor.execute("SELECT id FROM groups WHERE name = %s LIMIT 1", ("Gathering Place Managers",))
            gp_row = cursor.fetchone()
        if gp_row:
            gp_id = gp_row[0]
            cursor.execute("SELECT id FROM users WHERE role = 'Owner' ORDER BY id ASC LIMIT 1")
            owner_row = cursor.fetchone()
            if owner_row:
                cursor.execute("""
                    INSERT IGNORE INTO user_groups (user_id, group_id, role_in_group, assigned_by)
                    VALUES (%s, %s, 'member', %s)
                """, (owner_row[0], gp_id, owner_row[0]))
    except Exception as e:
        print(f"Gathering Place Managers owner seed note: {e}")