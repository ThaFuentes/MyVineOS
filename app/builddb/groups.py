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

    # ----- USER_PERMISSIONS (direct per-person YES grants) -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id INT UNSIGNED NOT NULL,
            permission_key VARCHAR(64) NOT NULL,
            granted_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, permission_key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    try:
        cursor.execute("CREATE INDEX idx_user_permissions_key ON user_permissions(permission_key)")
    except Exception:
        pass

    # ----- USER_PERMISSION_BLOCKS (explicit NO — beats groups) -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_permission_blocks (
            user_id INT UNSIGNED NOT NULL,
            permission_key VARCHAR(64) NOT NULL,
            blocked_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, permission_key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (blocked_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    try:
        cursor.execute("CREATE INDEX idx_user_permission_blocks_key ON user_permission_blocks(permission_key)")
    except Exception:
        pass

    # ----- SEED START TEMPLATES (Member / Staff) — fine-grained defaults, not role ladders -----
    try:
        import json
        from app.utils.permission_matrix import SYSTEM_TEMPLATE_GROUPS
        for tmpl in SYSTEM_TEMPLATE_GROUPS:
            perms_json = json.dumps(tmpl.get('permissions') or [])
            cursor.execute(
                "SELECT id FROM groups WHERE system_key = %s OR name = %s LIMIT 1",
                (tmpl['system_key'], tmpl['name']),
            )
            row = cursor.fetchone()
            if row:
                gid = row[0] if not isinstance(row, dict) else row.get('id')
                cursor.execute(
                    """
                    UPDATE groups
                       SET description = %s,
                           permissions = %s,
                           system_key = %s,
                           visibility = 'private'
                     WHERE id = %s
                    """,
                    (tmpl['description'], perms_json, tmpl['system_key'], gid),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO groups (name, description, visibility, permissions, system_key)
                    VALUES (%s, %s, 'private', %s, %s)
                    """,
                    (tmpl['name'], tmpl['description'], perms_json, tmpl['system_key']),
                )
                print(f"Seeded access template group: {tmpl['name']}")
    except Exception as e:
        print(f"Warning: could not seed access template groups: {e}")

    # ----- SEED ESSENTIAL SYSTEM GROUPS -----
    # Using INSERT IGNORE - safe to run repeatedly (name is UNIQUE).
    # All new Ticket groups added here. Pastoral and Worship left untouched.
    # Permission Groups for enterprise RBAC.
    # Admins put Staff/Members into these groups to grant capabilities.
    # INSERT IGNORE is name-unique; UPDATE below refreshes keys for known system groups.
    essential_groups = [
        (
            "Ticket Managers",
            "Full ticket/helpdesk managers (see ALL tickets, assign, stats).",
            "private",
            '["manage_tickets"]',
        ),
        (
            "Ticket IT Group",
            "IT/Support tickets only (computers, software, app issues).",
            "private",
            '["submit_tickets"]',
        ),
        (
            "Ticket Maintenance Group",
            "Building/property tickets (repairs, cleaning, facility requests).",
            "private",
            '["submit_tickets"]',
        ),
        (
            "Ticket Memberships Group",
            "Membership tickets (new members, profile updates, family linking).",
            "private",
            '["submit_tickets"]',
        ),
        (
            "Ticket General Group",
            "Volunteers: unassigned General tickets and own assignments only.",
            "private",
            '["submit_tickets"]',
        ),
        (
            "Finance Team",
            "Full financials: accounting ledger, bills, and donation management. "
            "Add only trusted finance staff.",
            "private",
            '["manage_accounting", "manage_bills", "manage_donations", "view_donations"]',
        ),
        (
            "Donations Clerks",
            "Record and view donations only — no full accounting suite.",
            "private",
            '["manage_donations", "view_donations"]',
        ),
        (
            "Bills Managers",
            "Recurring bills only (no donations management / full ledger).",
            "private",
            '["manage_bills"]',
        ),
        (
            "Pastoral Group",
            "Pastoral care area (sensitive). Membership grants access_pastoral.",
            "private",
            '["access_pastoral"]',
        ),
        (
            "Worship Team Group",
            "Worship songs, setlists, plans, and music studio.",
            "private",
            '["access_worship", "manage_worship"]',
        ),
        (
            "Gathering Place Managers",
            "Protected system group - access to The Gathering Place Manager (site-wide content moderation). "
            "Only the Owner may add members; Admins already in this group may also add members. "
            "Regular group members cannot add others.",
            "private",
            '["moderate_announcements", "moderate_events", "moderate_sermons", "moderate_prayers", "moderate_dreams", "moderate_prophecies"]',
        ),
    ]
    for name, desc, visibility, perms in essential_groups:
        cursor.execute("""
            INSERT IGNORE INTO groups (name, description, visibility, permissions)
            VALUES (%s, %s, %s, %s)
        """, (name, desc, visibility, perms))
    print(
        "Groups seeded (if not already present): Ticket*, Finance Team, Donations Clerks, "
        "Bills Managers, Pastoral Group, Worship Team Group, Gathering Place Managers."
    )

    # Stable system keys + refresh permission JSON for known enterprise groups
    # (does not remove members; only upgrades capability keys / system_key).
    system_group_updates = [
        ("Finance Team", "finance_team",
         '["manage_accounting", "manage_bills", "manage_donations", "view_donations"]'),
        ("Donations Clerks", "donations_clerks",
         '["manage_donations", "view_donations"]'),
        ("Bills Managers", "bills_managers", '["manage_bills"]'),
        ("Pastoral Group", "pastoral", '["access_pastoral"]'),
        ("Worship Team Group", "worship_team", '["access_worship", "manage_worship"]'),
        ("Gathering Place Managers", "gathering_place",
         '["moderate_announcements", "moderate_events", "moderate_sermons", "moderate_prayers", "moderate_dreams", "moderate_prophecies"]'),
        ("Ticket Managers", "ticket_managers", '["manage_tickets"]'),
    ]
    try:
        for name, skey, perms in system_group_updates:
            cursor.execute(
                """
                UPDATE groups
                SET system_key = COALESCE(NULLIF(system_key, ''), %s),
                    permissions = %s,
                    description = COALESCE(NULLIF(description, ''), description)
                WHERE name = %s
                """,
                (skey, perms, name),
            )
        cursor.execute("""
            UPDATE groups SET system_key = 'gathering_place'
            WHERE system_key IS NULL AND description LIKE %s
        """, ('%Protected system group - access to The Gathering Place Manager%',))
    except Exception as e:
        print(f"System group keys/permissions update note: {e}")

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