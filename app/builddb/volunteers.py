# Volunteer scheduling, rotations, skills, accept/decline, reminders.


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vol_skills (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(120) NOT NULL,
            description VARCHAR(500) NULL,
            active TINYINT(1) NOT NULL DEFAULT 1,
            UNIQUE KEY uq_vol_skill_name (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vol_teams (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(160) NOT NULL,
            description TEXT NULL,
            color VARCHAR(24) NOT NULL DEFAULT '#22d3ee',
            active TINYINT(1) NOT NULL DEFAULT 1,
            sort_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_vol_team_name (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vol_roles (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            team_id INT UNSIGNED NOT NULL,
            name VARCHAR(160) NOT NULL,
            description VARCHAR(500) NULL,
            slots INT UNSIGNED NOT NULL DEFAULT 1,
            required_skill_id INT UNSIGNED NULL,
            sort_order INT NOT NULL DEFAULT 0,
            active TINYINT(1) NOT NULL DEFAULT 1,
            INDEX idx_vol_roles_team (team_id),
            CONSTRAINT fk_vol_roles_team
                FOREIGN KEY (team_id) REFERENCES vol_teams(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vol_person_skills (
            user_id INT UNSIGNED NOT NULL,
            skill_id INT UNSIGNED NOT NULL,
            PRIMARY KEY (user_id, skill_id),
            CONSTRAINT fk_vol_ps_skill
                FOREIGN KEY (skill_id) REFERENCES vol_skills(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vol_team_members (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            team_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            preferred_role_id INT UNSIGNED NULL,
            notes VARCHAR(500) NULL,
            active TINYINT(1) NOT NULL DEFAULT 1,
            UNIQUE KEY uq_vol_team_user (team_id, user_id),
            CONSTRAINT fk_vol_tm_team
                FOREIGN KEY (team_id) REFERENCES vol_teams(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vol_events (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            title VARCHAR(255) NOT NULL,
            event_date DATE NOT NULL,
            start_time TIME NULL,
            end_time TIME NULL,
            location VARCHAR(255) NULL,
            notes TEXT NULL,
            team_id INT UNSIGNED NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'open',
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_vol_events_date (event_date, status),
            INDEX idx_vol_events_team (team_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vol_assignments (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            event_id INT UNSIGNED NOT NULL,
            role_id INT UNSIGNED NULL,
            role_name VARCHAR(160) NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            response_token VARCHAR(64) NOT NULL,
            response_note VARCHAR(500) NULL,
            responded_at TIMESTAMP NULL,
            reminded_at TIMESTAMP NULL,
            assigned_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_vol_assign_token (response_token),
            UNIQUE KEY uq_vol_assign_event_user_role (event_id, user_id, role_name),
            INDEX idx_vol_assign_user (user_id, status),
            INDEX idx_vol_assign_event (event_id, status),
            INDEX idx_vol_assign_status (status),
            CONSTRAINT fk_vol_assign_event
                FOREIGN KEY (event_id) REFERENCES vol_events(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vol_rotations (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            team_id INT UNSIGNED NOT NULL,
            role_id INT UNSIGNED NULL,
            role_name VARCHAR(160) NOT NULL,
            name VARCHAR(160) NOT NULL,
            frequency VARCHAR(24) NOT NULL DEFAULT 'weekly',
            member_ids_json MEDIUMTEXT NOT NULL,
            cursor_index INT NOT NULL DEFAULT 0,
            active TINYINT(1) NOT NULL DEFAULT 1,
            notes VARCHAR(500) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_vol_rot_team (team_id, active),
            CONSTRAINT fk_vol_rot_team
                FOREIGN KEY (team_id) REFERENCES vol_teams(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Settings for reminder windows
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
    """)
    scols = {row[0] for row in cursor.fetchall()}
    for name, definition in {
        'vol_reminders_enabled': "TINYINT(1) NOT NULL DEFAULT 1",
        'vol_reminder_days_before': "INT NOT NULL DEFAULT 3",
        'vol_auto_notify_on_assign': "TINYINT(1) NOT NULL DEFAULT 1",
    }.items():
        if name not in scols:
            print(f"Migration: Adding settings.{name}")
            cursor.execute(f"ALTER TABLE settings ADD COLUMN {name} {definition}")

    # Seed common teams / skills if empty
    cursor.execute("SELECT COUNT(*) FROM vol_teams")
    n = cursor.fetchone()[0]
    if not n:
        seeds = [
            ('Greeters', 'Welcome people at the doors', '#34d399', 10),
            ('Ushers', 'Seating, offering, assistance', '#22d3ee', 20),
            ('Parking', 'Lot & traffic help', '#a78bfa', 30),
            ('Kids Check-In', 'Family ministry desk support', '#f472b6', 40),
            ('Hospitality', 'Coffee, snacks, fellowship', '#fb923c', 50),
            ('Tech / Media', 'Audio, video, livestream', '#fbbf24', 60),
            ('Prayer Team', 'Ministry of prayer', '#60a5fa', 70),
        ]
        for name, desc, color, sort in seeds:
            cursor.execute(
                "INSERT INTO vol_teams (name, description, color, sort_order) VALUES (%s,%s,%s,%s)",
                (name, desc, color, sort),
            )
        # Default roles for greeters
        cursor.execute("SELECT id FROM vol_teams WHERE name='Greeters' LIMIT 1")
        row = cursor.fetchone()
        if row:
            tid = row[0]
            for rn, slots, so in [('Front Door', 2, 1), ('Lobby', 1, 2)]:
                cursor.execute(
                    "INSERT INTO vol_roles (team_id, name, slots, sort_order) VALUES (%s,%s,%s,%s)",
                    (tid, rn, slots, so),
                )

    cursor.execute("SELECT COUNT(*) FROM vol_skills")
    n = cursor.fetchone()[0]
    if not n:
        for sk in (
            'First-time greeter', 'CPR certified', 'Sound board', 'Camera / video',
            'Kids ministry', 'Driving', 'Spanish speaking', 'Sign language',
        ):
            cursor.execute("INSERT INTO vol_skills (name) VALUES (%s)", (sk,))
