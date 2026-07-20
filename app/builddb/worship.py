# Worship Team - songs, setlists, rehearsals, assignments, presentation.


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_songs (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            title VARCHAR(255) NOT NULL,
            artist VARCHAR(255) NULL,
            ccli_song_number VARCHAR(32) NULL,
            copyright_line VARCHAR(500) NULL,
            publisher VARCHAR(255) NULL,
            copyright_year SMALLINT UNSIGNED NULL,
            lyrics_raw LONGTEXT NULL,
            sections_json LONGTEXT NOT NULL,
            chords_filename VARCHAR(255) NULL,
            notes_permanent TEXT NULL,
            created_by INT UNSIGNED NULL,
            updated_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_default_assignments (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            role_name VARCHAR(120) NOT NULL,
            user_id INT UNSIGNED NULL,
            guest_name VARCHAR(160) NULL,
            UNIQUE KEY uq_worship_default_role (role_name),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)
    # Migration: non-member guests on worship defaults / setlist assignments
    for table in (
        'worship_default_assignments',
        'worship_setlist_assignments',
        'worship_weekly_template_assignments',
        'worship_template_assignments',
    ):
        try:
            cursor.execute(f"""
                SELECT IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = 'user_id'
            """, (table,))
            row = cursor.fetchone()
            if row and str(row[0] if not isinstance(row, dict) else row.get('IS_NULLABLE')).upper() == 'NO':
                cursor.execute(f"ALTER TABLE {table} MODIFY COLUMN user_id INT UNSIGNED NULL")
                print(f"Migration: {table}.user_id nullable (guest support)")
        except Exception as e:
            print(f"  (skip {table} user_id nullable: {e})")
        try:
            cursor.execute(f"""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = 'guest_name'
            """, (table,))
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN guest_name VARCHAR(160) NULL")
                print(f"Migration: {table}.guest_name added")
        except Exception as e:
            print(f"  (skip {table} guest_name: {e})")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_rehearsal_templates (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            weekday TINYINT UNSIGNED NOT NULL,
            title VARCHAR(255) NOT NULL,
            rehearsal_time TIME NULL,
            service_time TIME NULL,
            location VARCHAR(255) NULL,
            notes TEXT NULL,
            created_by INT UNSIGNED NULL,
            UNIQUE KEY uq_worship_rehearsal_weekday (weekday),
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_template_assignments (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            template_id INT UNSIGNED NOT NULL,
            role_name VARCHAR(120) NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            FOREIGN KEY (template_id) REFERENCES worship_rehearsal_templates(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_setlists (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            service_date DATE NULL,
            title VARCHAR(255) NOT NULL,
            service_time TIME NULL,
            rehearsal_time TIME NULL,
            rehearsal_location VARCHAR(255) NULL,
            notes TEXT NULL,
            is_published TINYINT(1) NOT NULL DEFAULT 0,
            created_by INT UNSIGNED NULL,
            updated_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_setlist_assignments (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            setlist_id INT UNSIGNED NOT NULL,
            role_name VARCHAR(120) NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            FOREIGN KEY (setlist_id) REFERENCES worship_setlists(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_setlist_songs (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            setlist_id INT UNSIGNED NOT NULL,
            song_id INT UNSIGNED NOT NULL,
            sort_order INT UNSIGNED NOT NULL DEFAULT 0,
            arrangement_json LONGTEXT NULL,
            session_notes TEXT NULL,
            keep_session_notes TINYINT(1) NOT NULL DEFAULT 0,
            song_key VARCHAR(16) NULL,
            FOREIGN KEY (setlist_id) REFERENCES worship_setlists(id) ON DELETE CASCADE,
            FOREIGN KEY (song_id) REFERENCES worship_songs(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_weekly_templates (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            weekday TINYINT UNSIGNED NOT NULL,
            title VARCHAR(255) NOT NULL,
            service_time TIME NULL,
            rehearsal_time TIME NULL,
            rehearsal_location VARCHAR(255) NULL,
            notes TEXT NULL,
            public_token VARCHAR(48) NULL,
            created_by INT UNSIGNED NULL,
            updated_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_worship_weekly_weekday (weekday),
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_weekly_template_songs (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            template_id INT UNSIGNED NOT NULL,
            song_id INT UNSIGNED NOT NULL,
            sort_order INT UNSIGNED NOT NULL DEFAULT 0,
            arrangement_json LONGTEXT NULL,
            song_key VARCHAR(16) NULL,
            FOREIGN KEY (template_id) REFERENCES worship_weekly_templates(id) ON DELETE CASCADE,
            FOREIGN KEY (song_id) REFERENCES worship_songs(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_weekly_template_assignments (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            template_id INT UNSIGNED NOT NULL,
            role_name VARCHAR(120) NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            FOREIGN KEY (template_id) REFERENCES worship_weekly_templates(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_member_notes (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            setlist_id INT UNSIGNED NULL,
            template_id INT UNSIGNED NULL,
            user_id INT UNSIGNED NOT NULL,
            note_text TEXT NOT NULL,
            created_by INT UNSIGNED NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_worship_note_setlist_user (setlist_id, user_id),
            UNIQUE KEY uq_worship_note_template_user (template_id, user_id),
            FOREIGN KEY (setlist_id) REFERENCES worship_setlists(id) ON DELETE CASCADE,
            FOREIGN KEY (template_id) REFERENCES worship_weekly_templates(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_song_plays (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            song_id INT UNSIGNED NOT NULL,
            setlist_id INT UNSIGNED NULL,
            service_date DATE NOT NULL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            recorded_by INT UNSIGNED NULL,
            FOREIGN KEY (song_id) REFERENCES worship_songs(id) ON DELETE CASCADE,
            FOREIGN KEY (setlist_id) REFERENCES worship_setlists(id) ON DELETE SET NULL,
            FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_worship_plays_song (song_id),
            INDEX idx_worship_plays_date (service_date)
        ) ENGINE=InnoDB;
    """)


    for col_sql in (
        "ALTER TABLE worship_setlists ADD COLUMN public_token VARCHAR(48) NULL",
        "ALTER TABLE worship_setlists ADD COLUMN service_confirmed_at TIMESTAMP NULL",
        # Default prompter order for a song (section ids, may repeat e.g. chorus twice)
        "ALTER TABLE worship_songs ADD COLUMN play_order_json LONGTEXT NULL",
        "ALTER TABLE worship_songs ADD COLUMN default_key VARCHAR(16) NULL",
        "ALTER TABLE worship_songs ADD COLUMN rights_notes TEXT NULL",
    ):
        try:
            cursor.execute(col_sql)
        except Exception:
            pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_song_charts (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            song_id INT UNSIGNED NOT NULL,
            chart_key VARCHAR(40) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            instrument_family VARCHAR(32) NOT NULL DEFAULT 'full',
            is_primary TINYINT(1) NOT NULL DEFAULT 0,
            show_chords TINYINT(1) NOT NULL DEFAULT 1,
            show_lyrics TINYINT(1) NOT NULL DEFAULT 1,
            capo SMALLINT NULL,
            notation VARCHAR(24) NOT NULL DEFAULT 'chordpro',
            sections_json LONGTEXT NOT NULL,
            play_order_json LONGTEXT NULL,
            chart_filename VARCHAR(255) NULL,
            notes TEXT NULL,
            created_by INT UNSIGNED NULL,
            updated_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_worship_song_chart (song_id, chart_key),
            FOREIGN KEY (song_id) REFERENCES worship_songs(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_worship_chart_song (song_id)
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_user_chart_notes (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            chart_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            note_text TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_worship_user_chart (chart_id, user_id),
            FOREIGN KEY (chart_id) REFERENCES worship_song_charts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worship_ccli_settings (
            id TINYINT UNSIGNED PRIMARY KEY DEFAULT 1,
            ccli_license_number VARCHAR(64) NULL,
            organization_name VARCHAR(255) NULL,
            notes TEXT NULL,
            updated_by INT UNSIGNED NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
    """)

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN accepts_worship_emails INTEGER DEFAULT 1")
    except Exception:
        pass

    try:
        cursor.execute("UPDATE groups SET system_key = 'worship_team' WHERE name = 'Worship Team Group' AND (system_key IS NULL OR system_key = '')")
    except Exception:
        pass

    print("Worship Team tables ready (songs, charts, setlists, weekly templates, play history).")
