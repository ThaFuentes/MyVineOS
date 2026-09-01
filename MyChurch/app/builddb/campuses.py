# Multi-campus support: campus registry, membership, campus_id on key tables.


def _ensure_column(cursor, table, name, definition):
    cursor.execute(
        """
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (table, name),
    )
    if not cursor.fetchone():
        print(f"Migration: Adding {table}.{name}")
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        except Exception as e:
            print(f"  (skip {table}.{name}: {e})")


def _ensure_index(cursor, table, index_name, columns):
    try:
        cursor.execute(f"CREATE INDEX {index_name} ON {table}({columns})")
    except Exception:
        pass


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campuses (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            code VARCHAR(32) NOT NULL,
            name VARCHAR(160) NOT NULL,
            short_name VARCHAR(80) NULL,
            address TEXT NULL,
            city VARCHAR(120) NULL,
            state VARCHAR(80) NULL,
            postal_code VARCHAR(24) NULL,
            phone VARCHAR(40) NULL,
            email VARCHAR(255) NULL,
            pastor_name VARCHAR(160) NULL,
            timezone VARCHAR(64) NULL,
            color VARCHAR(24) NOT NULL DEFAULT '#22d3ee',
            is_primary TINYINT(1) NOT NULL DEFAULT 0,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            sort_order INT NOT NULL DEFAULT 0,
            notes TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_campus_code (code),
            INDEX idx_campus_active (is_active, sort_order)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campus_members (
            campus_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            is_home TINYINT(1) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (campus_id, user_id),
            INDEX idx_campus_members_user (user_id),
            CONSTRAINT fk_campus_members_campus
                FOREIGN KEY (campus_id) REFERENCES campuses(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Global multi-campus flag on settings
    _ensure_column(cursor, 'settings', 'multi_campus_enabled', "TINYINT(1) NOT NULL DEFAULT 0")
    _ensure_column(cursor, 'settings', 'default_campus_id', "INT UNSIGNED NULL")
    # When 1: only Admin/Owner may use "All campuses" in the switcher (isolates branch staff by default)
    _ensure_column(cursor, 'settings', 'campus_all_view_admin_only', "TINYINT(1) NOT NULL DEFAULT 0")

    # Per-branch: keep this campus's content private from other campuses
    _ensure_column(cursor, 'campuses', 'content_isolation', "TINYINT(1) NOT NULL DEFAULT 0")

    # Users: primary / home campus
    _ensure_column(cursor, 'users', 'primary_campus_id', "INT UNSIGNED NULL")
    _ensure_index(cursor, 'users', 'idx_users_primary_campus', 'primary_campus_id')

    # Domain tables (nullable campus_id = org-wide / unassigned)
    for table in (
        'events',
        'attendance',
        'donations',
        'groups',
        'announcements',
        'sermons',
        'prayers',
        'dreams',
        'prophecies',
        'vol_events',
        'vol_teams',
        'child_classrooms',
        'child_checkins',
        'curriculum_series',
        'acct_expenses',
        'acct_journal_entries',
        'acct_budgets',
        'worship_setlists',
        'service_plans',
        'service_templates',
        'recurring_bills',
        'inventory_batches',
        # Pastoral creator content — scoped so isolated branches do not intermingle
        'pastoral_sermons',
        'illustration_library',
        'pastoral_vault',
        'pastoral_care_requests',
        'bible_notes',
    ):
        # Only alter if table exists
        cursor.execute(
            """
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table,),
        )
        if not cursor.fetchone():
            continue
        _ensure_column(cursor, table, 'campus_id', "INT UNSIGNED NULL")
        _ensure_index(cursor, table, f'idx_{table}_campus', 'campus_id')

    # Seed primary campus from church settings if none
    cursor.execute("SELECT COUNT(*) FROM campuses")
    n = cursor.fetchone()[0]
    if not n:
        cursor.execute("SELECT church_name, address, phone_number FROM settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            if isinstance(row, dict):
                cname = row.get('church_name') or 'Main Campus'
                addr = row.get('address')
                phone = row.get('phone_number')
            else:
                cname = row[0] or 'Main Campus'
                addr = row[1] if len(row) > 1 else None
                phone = row[2] if len(row) > 2 else None
        else:
            cname, addr, phone = 'Main Campus', None, None
        cursor.execute(
            """
            INSERT INTO campuses (code, name, short_name, address, phone, is_primary, is_active, sort_order)
            VALUES ('MAIN', %s, 'Main', %s, %s, 1, 1, 0)
            """,
            ((cname or 'Main Campus')[:160], addr, phone),
        )
        print("Seeded primary campus from church settings.")
